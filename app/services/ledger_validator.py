import uuid
from decimal import Decimal
from typing import Iterable, Sequence, Union
from app.models.posting import Posting, PostingDirection
from app.schemas.transaction import PostingCreate


class LedgerException(Exception):
    """Base exception for ledger operations."""
    pass


class UnbalancedLedgerError(LedgerException):
    """Raised when sum(Debits) != sum(Credits) in a transaction."""
    def __init__(self, total_debits: Decimal, total_credits: Decimal):
        diff = total_debits - total_credits
        super().__init__(
            f"Double-entry ledger invariant violation: "
            f"Total Debits ({total_debits}) != Total Credits ({total_credits}). "
            f"Imbalance: {diff}"
        )
        self.total_debits = total_debits
        self.total_credits = total_credits
        self.diff = diff


class InsufficientBalanceError(LedgerException):
    """Raised when an account does not have sufficient funds for a debit posting."""
    def __init__(self, account_id: uuid.UUID, current_balance: Decimal, requested_amount: Decimal):
        super().__init__(
            f"Account {account_id} has insufficient balance. "
            f"Current: {current_balance}, Requested: {requested_amount}"
        )
        self.account_id = account_id
        self.current_balance = current_balance
        self.requested_amount = requested_amount


class AccountCurrencyMismatchError(LedgerException):
    """Raised when a transfer is attempted between accounts with mismatched currencies."""
    def __init__(self, source_curr: str, dest_curr: str):
        super().__init__(
            f"Currency mismatch: Source currency '{source_curr}' does not match "
            f"Destination currency '{dest_curr}'"
        )


def assert_balanced_postings(
    postings: Sequence[Union[Posting, PostingCreate]]
) -> None:
    """
    Enforces the fundamental double-entry invariant:
    sum(Debits) == sum(Credits)

    Raises:
        ValueError: If fewer than 2 postings are supplied.
        UnbalancedLedgerError: If the transaction is unbalanced.
    """
    if len(postings) < 2:
        raise ValueError(
            f"Double-entry transaction requires at least 2 postings, got {len(postings)}"
        )

    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")

    for p in postings:
        amount = Decimal(str(p.amount))
        if amount <= Decimal("0.00"):
            raise ValueError(f"Posting amount must be strictly positive, got {amount}")

        if p.direction == PostingDirection.DEBIT:
            total_debits += amount
        elif p.direction == PostingDirection.CREDIT:
            total_credits += amount
        else:
            raise ValueError(f"Unknown posting direction: {p.direction}")

    if total_debits != total_credits:
        raise UnbalancedLedgerError(total_debits=total_debits, total_credits=total_credits)


def sort_account_ids_for_locking(account_ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    """
    Deterministically sorts account UUIDs in lexicographical order.
    Acquiring locks in this consistent global order mathematically prevents
    PostgreSQL deadlocks under concurrent multi-account transactions.
    """
    return sorted(list(set(account_ids)))
