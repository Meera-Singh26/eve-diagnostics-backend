from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: int = Field(gt=0)
    # lets a client (or a test) force the result of the fake gateway.
    # PENDING means "the provider will tell us later through the webhook".
    simulate_outcome: PaymentStatus | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    reference: str
    amount: Decimal
    status: PaymentStatus
    created_at: datetime


class WebhookPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    payment_reference: str = Field(min_length=1, max_length=64)
    status: Literal["SUCCESS", "FAILED"]
    amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)


class WebhookAck(BaseModel):
    status: Literal["processed", "duplicate"]
    event_id: str
    outcome: str | None = None
