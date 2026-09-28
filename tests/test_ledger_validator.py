import uuid
from decimal import Decimal
import pytest
from app.models.posting import PostingDirection
from app.schemas.transaction import PostingCreate
from app.services.ledger_validator import (
    assert_balanced_postings,
    sort_account_ids_for_locking,
    UnbalancedLedgerError,
)


def test_balanced_postings_success():
    account_a = uuid.uuid4()
    account_b = uuid.uuid4()

    postings = [
        PostingCreate(account_id=account_a, direction=PostingDirection.DEBIT, amount=Decimal("150.50")),
        PostingCreate(account_id=account_b, direction=PostingDirection.CREDIT, amount=Decimal("150.50")),
    ]

    # Should not raise any exception
    assert_balanced_postings(postings)


def test_multi_leg_balanced_postings():
    acc_payer = uuid.uuid4()
    acc_merchant = uuid.uuid4()
    acc_fee = uuid.uuid4()

    postings = [
        PostingCreate(account_id=acc_payer, direction=PostingDirection.DEBIT, amount=Decimal("100.00")),
        PostingCreate(account_id=acc_merchant, direction=PostingDirection.CREDIT, amount=Decimal("98.00")),
        PostingCreate(account_id=acc_fee, direction=PostingDirection.CREDIT, amount=Decimal("2.00")),
    ]

    # 100.00 == 98.00 + 2.00
    assert_balanced_postings(postings)


def test_unbalanced_postings_raises_error():
    account_a = uuid.uuid4()
    account_b = uuid.uuid4()

    postings = [
        PostingCreate(account_id=account_a, direction=PostingDirection.DEBIT, amount=Decimal("150.50")),
        PostingCreate(account_id=account_b, direction=PostingDirection.CREDIT, amount=Decimal("149.00")),
    ]

    with pytest.raises(UnbalancedLedgerError) as exc_info:
        assert_balanced_postings(postings)

    assert exc_info.value.total_debits == Decimal("150.50")
    assert exc_info.value.total_credits == Decimal("149.00")
    assert exc_info.value.diff == Decimal("1.50")


def test_insufficient_postings_count():
    account_a = uuid.uuid4()
    single_posting = [
        PostingCreate(account_id=account_a, direction=PostingDirection.DEBIT, amount=Decimal("50.00"))
    ]

    with pytest.raises(ValueError, match="at least 2 postings"):
        assert_balanced_postings(single_posting)


def test_sort_account_ids_for_locking():
    id_1 = uuid.UUID("33333333-3333-3333-3333-333333333333")
    id_2 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    id_3 = uuid.UUID("22222222-2222-2222-2222-222222222222")

    sorted_ids = sort_account_ids_for_locking([id_1, id_2, id_3])
    assert sorted_ids == [id_2, id_3, id_1]

    # Test deduplication
    sorted_unique = sort_account_ids_for_locking([id_1, id_2, id_1])
    assert sorted_unique == [id_2, id_1]
