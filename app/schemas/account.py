import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    user_id: uuid.UUID
    currency: str = Field(default="INR", min_length=3, max_length=3)
    initial_balance: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Initial deposit balance, must be non-negative",
    )


class AccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    balance: Decimal = Field(decimal_places=2)
    currency: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountBalanceResponse(BaseModel):
    id: uuid.UUID
    balance: Decimal = Field(decimal_places=2)
    currency: str
    version: int

    model_config = ConfigDict(from_attributes=True)
