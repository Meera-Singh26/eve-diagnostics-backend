from datetime import datetime, timezone
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus
from app.schemas.catalog import CentreBrief, TestOut
from app.schemas.payment import PaymentOut


class BookingCreate(BaseModel):
    centre_id: int = Field(gt=0)
    test_id: int = Field(gt=0)
    appointment_at: AwareDatetime

    @field_validator("appointment_at")
    @classmethod
    def must_be_in_future(cls, v: datetime) -> datetime:
        if v <= datetime.now(timezone.utc):
            raise ValueError("appointment_at must be in the future")
        return v


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    centre: CentreBrief
    test: TestOut
    appointment_at: datetime
    amount: Decimal
    status: BookingStatus
    created_at: datetime
    payments: list[PaymentOut]
