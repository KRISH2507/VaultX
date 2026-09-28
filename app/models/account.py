import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List
from sqlalchemy import CheckConstraint, Index, Numeric, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.posting import Posting


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    postings: Mapped[List["Posting"]] = relationship(
        "Posting",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="Posting.created_at.asc()",
    )

    __table_args__ = (
        CheckConstraint("balance >= 0.00", name="chk_accounts_balance_non_negative"),
        Index("ix_accounts_user_id_currency", "user_id", "currency"),
    )

    def __repr__(self) -> str:
        return f"<Account {self.id} | User: {self.user_id} | Balance: {self.balance} {self.currency}>"
