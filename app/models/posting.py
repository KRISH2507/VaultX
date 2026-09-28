import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.transaction import Transaction


class PostingDirection(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class Posting(Base):
    __tablename__ = "postings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    direction: Mapped[PostingDirection] = mapped_column(
        SAEnum(PostingDirection, name="posting_direction", native_enum=False),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    sequence_num: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        back_populates="postings",
    )
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="postings",
    )

    __table_args__ = (
        CheckConstraint("amount > 0.00", name="chk_postings_amount_positive"),
        Index("ix_postings_account_created_at", "account_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Posting {self.id} | Tx: {self.transaction_id} | "
            f"Account: {self.account_id} | {self.direction.value}: {self.amount}>"
        )
