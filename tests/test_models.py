import uuid
from decimal import Decimal
import pytest
from app.models import (
    Base,
    Account,
    Transaction,
    TransactionStatus,
    Posting,
    PostingDirection,
    IdempotencyKey,
    IdempotencyStatus,
    OutboxEvent,
    OutboxStatus,
)


def test_models_metadata_registered():
    tables = Base.metadata.tables.keys()
    assert "accounts" in tables
    assert "transactions" in tables
    assert "postings" in tables
    assert "idempotency_keys" in tables
    assert "outbox_events" in tables


def test_account_model_instantiation():
    acc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account = Account(
        id=acc_id,
        user_id=user_id,
        balance=Decimal("1000.00"),
        currency="INR",
        version=1,
    )
    assert account.id == acc_id
    assert account.user_id == user_id
    assert account.balance == Decimal("1000.00")
    assert account.currency == "INR"
    assert account.version == 1


def test_transaction_and_posting_models():
    tx_id = uuid.uuid4()
    acc_src = uuid.uuid4()
    acc_dest = uuid.uuid4()

    tx = Transaction(
        id=tx_id,
        idempotency_key="tx-test-key-12345",
        source_account_id=acc_src,
        destination_account_id=acc_dest,
        amount=Decimal("250.00"),
        status=TransactionStatus.PENDING,
        description="Transfer test",
    )

    debit_posting = Posting(
        transaction_id=tx_id,
        account_id=acc_src,
        direction=PostingDirection.DEBIT,
        amount=Decimal("250.00"),
        balance_after=Decimal("750.00"),
        sequence_num=0,
    )

    credit_posting = Posting(
        transaction_id=tx_id,
        account_id=acc_dest,
        direction=PostingDirection.CREDIT,
        amount=Decimal("250.00"),
        balance_after=Decimal("250.00"),
        sequence_num=1,
    )

    assert tx.id == tx_id
    assert tx.idempotency_key == "tx-test-key-12345"
    assert debit_posting.direction == PostingDirection.DEBIT
    assert credit_posting.direction == PostingDirection.CREDIT


def test_idempotency_key_model():
    key = IdempotencyKey(
        key="idemp-key-999",
        request_hash="sha256-dummy-hash",
        status=IdempotencyStatus.IN_PROGRESS,
    )
    assert key.key == "idemp-key-999"
    assert key.status == IdempotencyStatus.IN_PROGRESS


def test_outbox_event_model():
    tx_id = uuid.uuid4()
    outbox = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=tx_id,
        event_type="TRANSACTION_COMMITTED",
        payload={"tx_id": str(tx_id), "amount": "250.00"},
        status=OutboxStatus.PENDING,
        transaction_id=tx_id,
    )
    assert outbox.aggregate_type == "TRANSACTION"
    assert outbox.status == OutboxStatus.PENDING
    assert outbox.payload["amount"] == "250.00"
