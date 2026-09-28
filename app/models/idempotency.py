from datetime import datetime
from enum import Enum
from typing import Any, Optional
from sqlalchemy import DateTime, Integer, JSON, String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    response_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    response_body: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    status: Mapped[IdempotencyStatus] = mapped_column(
        SAEnum(IdempotencyStatus, name="idempotency_status", native_enum=False),
        nullable=False,
        default=IdempotencyStatus.IN_PROGRESS,
        index=True,
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.key} | Status: {self.status.value}>"
