import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.posting import PostingDirection
from app.models.transaction import TransactionStatus


class PostingCreate(BaseModel):
    account_id: uuid.UUID
    direction: PostingDirection
    amount: Decimal = Field(gt=Decimal("0.00"), decimal_places=2)


class PostingResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    account_id: uuid.UUID
    direction: PostingDirection
    amount: Decimal = Field(decimal_places=2)
    balance_after: Decimal = Field(decimal_places=2)
    sequence_num: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransferCreate(BaseModel):
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    amount: Decimal = Field(
        gt=Decimal("0.00"),
        decimal_places=2,
        description="Transfer amount must be strictly positive",
    )
    currency: str = Field(default="INR", min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_distinct_accounts(self) -> "TransferCreate":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source_account_id and destination_account_id must be distinct")
        return self


class TransactionResponse(BaseModel):
    id: uuid.UUID
    idempotency_key: str
    source_account_id: Optional[uuid.UUID]
    destination_account_id: Optional[uuid.UUID]
    amount: Decimal = Field(decimal_places=2)
    status: TransactionStatus
    description: Optional[str]
    created_at: datetime
    postings: List[PostingResponse] = []

    model_config = ConfigDict(from_attributes=True)
