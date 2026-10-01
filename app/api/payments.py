import json

from fastapi import APIRouter, Depends
from fastapi.exceptions import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verified_webhook_body
from app.db.session import get_db
from app.models import User
from app.schemas.payment import PaymentCreate, PaymentOut, WebhookAck, WebhookPayload
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/", response_model=PaymentOut, status_code=201)
def make_payment(
    data: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return payments.create_payment(db, user, data.booking_id, data.simulate_outcome)


@router.post("/webhook/", response_model=WebhookAck)
def payment_webhook(body: bytes = Depends(verified_webhook_body), db: Session = Depends(get_db)):
    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        detail = json.loads(exc.json(include_url=False, include_context=False, include_input=False))
        raise HTTPException(status_code=422, detail=detail)

    ack, outcome = payments.process_webhook(db, payload)
    return WebhookAck(status=ack, event_id=payload.event_id, outcome=outcome)


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return payments.get_payment(db, user, payment_id)
