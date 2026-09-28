"""Initial financial ledger schema

Revision ID: 0001_initial_ledger_schema
Revises: 
Create Date: 2026-09-28 10:57:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_ledger_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Accounts Table
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("balance", sa.Numeric(15, 2), nullable=False, server_default="0.00"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint("balance >= 0.00", name="chk_accounts_balance_non_negative"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])
    op.create_index("ix_accounts_user_id_currency", "accounts", ["user_id", "currency"])

    # 2. Transactions Table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], name="fk_transactions_source_account_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_account_id"], ["accounts.id"], name="fk_transactions_destination_account_id", ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0.00", name="chk_transactions_amount_positive"),
        sa.UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
    )
    op.create_index("ix_transactions_idempotency_key", "transactions", ["idempotency_key"])
    op.create_index("ix_transactions_source_account_id", "transactions", ["source_account_id"])
    op.create_index("ix_transactions_destination_account_id", "transactions", ["destination_account_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index("ix_transactions_created_at", "transactions", ["created_at"])
    op.create_index("ix_transactions_status_created_at", "transactions", ["status", "created_at"])

    # 3. Postings Table
    op.create_table(
        "postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("sequence_num", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], name="fk_postings_transaction_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_postings_account_id", ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0.00", name="chk_postings_amount_positive"),
    )
    op.create_index("ix_postings_transaction_id", "postings", ["transaction_id"])
    op.create_index("ix_postings_account_id", "postings", ["account_id"])
    op.create_index("ix_postings_created_at", "postings", ["created_at"])
    op.create_index("ix_postings_account_created_at", "postings", ["account_id", "created_at"])

    # 4. Idempotency Keys Table
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_idempotency_keys_request_hash", "idempotency_keys", ["request_hash"])
    op.create_index("ix_idempotency_keys_status", "idempotency_keys", ["status"])

    # 5. Outbox Events Table
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(50), nullable=False, server_default="TRANSACTION"),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], name="fk_outbox_events_transaction_id", ondelete="CASCADE"),
    )
    op.create_index("ix_outbox_events_aggregate_type", "outbox_events", ["aggregate_type"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_outbox_events_transaction_id", "outbox_events", ["transaction_id"])
    op.create_index("ix_outbox_events_created_at", "outbox_events", ["created_at"])
    op.create_index("ix_outbox_events_status_created_at", "outbox_events", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("idempotency_keys")
    op.drop_table("postings")
    op.drop_table("transactions")
    op.drop_table("accounts")
