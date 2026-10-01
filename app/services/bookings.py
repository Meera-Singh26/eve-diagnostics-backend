from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Booking, BookingStatus, CentreTest, User
from app.schemas.booking import BookingCreate
from app.schemas.common import PageParams

_ALLOWED_MOVES = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.CANCELLED},
    # a failed payment can be retried, so FAILED is not a dead end
    BookingStatus.FAILED: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
}


def move_to(booking: Booking, new_status: BookingStatus) -> None:
    if booking.status == new_status:
        return
    if new_status not in _ALLOWED_MOVES[booking.status]:
        raise ConflictError(f"Booking cannot go from {booking.status.value} to {new_status.value}")
    booking.status = new_status


def create_booking(db: Session, user: User, data: BookingCreate) -> Booking:
    offering = db.scalar(
        select(CentreTest).where(CentreTest.centre_id == data.centre_id, CentreTest.test_id == data.test_id)
    )
    if offering is None:
        raise NotFoundError("This centre does not offer the selected test")

    duplicate = db.scalar(
        select(Booking.id).where(
            Booking.user_id == user.id,
            Booking.centre_id == data.centre_id,
            Booking.test_id == data.test_id,
            Booking.appointment_at == data.appointment_at,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    if duplicate:
        raise ConflictError("You already have a booking for this test at this time")

    booking = Booking(
        user_id=user.id,
        centre_id=data.centre_id,
        test_id=data.test_id,
        appointment_at=data.appointment_at,
        amount=offering.price,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    return get_booking(db, user, booking.id)


def get_booking(db: Session, user: User, booking_id: int) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    # someone else's booking looks the same as a missing one, so ids can't be probed
    if booking is None or booking.user_id != user.id:
        raise NotFoundError("Booking not found")
    return booking


def list_bookings(
    db: Session, user: User, page: PageParams, status: BookingStatus | None
) -> tuple[list[Booking], int]:
    stmt = select(Booking).where(Booking.user_id == user.id)
    if status:
        stmt = stmt.where(Booking.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.order_by(Booking.id.desc()).limit(page.limit).offset(page.offset)).unique().all()
    return list(rows), total


def cancel_booking(db: Session, user: User, booking_id: int) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update(of=Booking))
    if booking is None or booking.user_id != user.id:
        raise NotFoundError("Booking not found")
    # cancelling twice is fine, move_to ignores a no-op
    move_to(booking, BookingStatus.CANCELLED)
    db.commit()
    return booking
