from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TestCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class CentreCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    city: str = Field(min_length=2, max_length=80)
    address: str = Field(min_length=3, max_length=255)

    @field_validator("name", "city", "address")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class OfferingCreate(BaseModel):
    test_id: int = Field(gt=0)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class OfferingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test: TestOut
    price: Decimal


class CentreBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str


class CentreOut(CentreBrief):
    address: str
    offerings: list[OfferingOut]
