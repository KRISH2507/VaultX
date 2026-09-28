import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="TRANSACTION",
        index=True,
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    status: Mapped[OutboxStatus] = mapped_column(
        SAEnum(OutboxStatus, name="outbox_status", native_enum=False),
        nullable=False,
        default=OutboxStatus.PENDING,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction",
        back_populates="outbox_events",
    )

    __table_args__ = (
        Index("ix_outbox_events_status_created_at", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OutboxEvent {self.id} | Type: {self.event_type} | "
            f"Status: {self.status.value} | Retries: {self.retry_count}>"
        )
