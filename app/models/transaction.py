import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.posting import Posting
    from app.models.outbox import OutboxEvent


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    REVERSED = "REVERSED"
    FAILED = "FAILED"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    source_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    destination_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status", native_enum=False),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    postings: Mapped[List["Posting"]] = relationship(
        "Posting",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="Posting.sequence_num.asc()",
    )
    outbox_events: Mapped[List["OutboxEvent"]] = relationship(
        "OutboxEvent",
        back_populates="transaction",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("amount > 0.00", name="chk_transactions_amount_positive"),
        Index("ix_transactions_status_created_at", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction {self.id} | Key: {self.idempotency_key} | "
            f"Amount: {self.amount} | Status: {self.status.value}>"
        )
