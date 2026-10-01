import logging
import random
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models import Booking, BookingStatus, Payment, PaymentStatus, User, WebhookEvent
from app.schemas.payment import WebhookPayload
from app.services.bookings import move_to

log = logging.getLogger(__name__)


class AmountMismatch(DomainError):
    status_code = 400
    code = "amount_mismatch"


def _lock_booking(db: Session, booking_id: int) -> Booking | None:
    return db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update(of=Booking))


def _other_success_exists(booking: Booking, payment: Payment) -> bool:
    return any(p.status == PaymentStatus.SUCCESS and p.id != payment.id for p in booking.payments)


def create_payment(
    db: Session, user: User, booking_id: int, outcome: PaymentStatus | None
) -> Payment:
    booking = _lock_booking(db, booking_id)
    if booking is None or booking.user_id != user.id:
        raise NotFoundError("Booking not found")
    if booking.status == BookingStatus.CONFIRMED:
        raise ConflictError("Booking is already paid")
    if booking.status == BookingStatus.CANCELLED:
        raise ConflictError("Booking is cancelled")
    if any(p.status == PaymentStatus.PENDING for p in booking.payments):
        raise ConflictError("A payment for this booking is still being processed")

    if outcome is None:
        ok = random.random() < settings.payment_success_rate
        outcome = PaymentStatus.SUCCESS if ok else PaymentStatus.FAILED

    payment = Payment(
        booking_id=booking.id,
        reference=f"pay_{uuid.uuid4().hex[:24]}",
        amount=booking.amount,
        status=outcome,
    )
    db.add(payment)
    if outcome == PaymentStatus.SUCCESS:
        move_to(booking, BookingStatus.CONFIRMED)
    elif outcome == PaymentStatus.FAILED:
        move_to(booking, BookingStatus.FAILED)
    db.commit()
    log.info("payment created", extra={"payment_id": payment.id, "booking_id": booking.id, "status": outcome.value})
    return payment


def get_payment(db: Session, user: User, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.booking.user_id != user.id:
        raise NotFoundError("Payment not found")
    return payment


def process_webhook(db: Session, payload: WebhookPayload) -> tuple[str, str | None]:
    """Returns (ack_status, outcome). Safe to call any number of times with the same event."""
    event = WebhookEvent(
        event_id=payload.event_id,
        payment_reference=payload.payment_reference,
        payload=payload.model_dump(mode="json"),
    )
    db.add(event)
    try:
        # the unique event_id decides who wins if the same event arrives twice at once
        db.flush()
    except IntegrityError:
        db.rollback()
        log.info("duplicate webhook event", extra={"event_id": payload.event_id})
        return "duplicate", None

    payment = db.scalar(select(Payment).where(Payment.reference == payload.payment_reference))
    if payment is None:
        # not stored, so the provider can retry once we know about the payment
        db.rollback()
        raise NotFoundError("Unknown payment reference")

    # payments are only ever changed while holding the booking lock
    booking = _lock_booking(db, payment.booking_id)
    db.refresh(payment)

    if payload.amount is not None and Decimal(payload.amount) != payment.amount:
        db.rollback()
        raise AmountMismatch("Webhook amount does not match the payment amount")

    outcome = _apply_status(booking, payment, PaymentStatus(payload.status))
    event.outcome = outcome
    db.commit()
    log.info(
        "webhook processed",
        extra={"event_id": payload.event_id, "payment_id": payment.id, "outcome": outcome},
    )
    return "processed", outcome


def _apply_status(booking: Booking, payment: Payment, new_status: PaymentStatus) -> str:
    if payment.status == new_status:
        return "no_change"
    if payment.status == PaymentStatus.SUCCESS:
        # money already taken, a later FAILED event is stale or wrong
        log.warning("ignoring status downgrade", extra={"payment_id": payment.id, "incoming": new_status.value})
        return "ignored_downgrade"

    if new_status == PaymentStatus.SUCCESS:
        if _other_success_exists(booking, payment):
            log.warning("second successful charge", extra={"booking_id": booking.id, "payment_id": payment.id})
            return "ignored_already_paid"
        payment.status = PaymentStatus.SUCCESS
        if booking.status == BookingStatus.CANCELLED:
            # paid after the user cancelled, needs a refund which is out of scope here
            log.warning("payment succeeded for cancelled booking", extra={"booking_id": booking.id})
            return "success_on_cancelled_booking"
        move_to(booking, BookingStatus.CONFIRMED)
        return "payment_success"

    payment.status = PaymentStatus.FAILED
    if booking.status == BookingStatus.PENDING:
        move_to(booking, BookingStatus.FAILED)
    return "payment_failed"
