import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction, TransactionStatus
from app.models.posting import Posting, PostingDirection
from app.models.outbox import OutboxEvent, OutboxStatus
from app.schemas.account import AccountCreate


class AccountNotFoundError(Exception):
    pass


class AccountService:
    @staticmethod
    async def create_account(
        db: AsyncSession,
        data: AccountCreate,
    ) -> Account:
        """Creates a new financial account."""
        account = Account(
            id=uuid.uuid4(),
            user_id=data.user_id,
            balance=data.initial_balance,
            currency=data.currency.upper(),
            version=1,
        )
        db.add(account)
        await db.flush()
        return account

    @staticmethod
    async def get_account(
        db: AsyncSession,
        account_id: uuid.UUID,
        for_update: bool = False,
    ) -> Account:
        """Retrieves an account by its UUID, optionally acquiring a row-level lock."""
        stmt = select(Account).where(Account.id == account_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            raise AccountNotFoundError(f"Account with ID '{account_id}' not found.")
        return account

    @staticmethod
    async def deposit(
        db: AsyncSession,
        account_id: uuid.UUID,
        amount: Decimal,
        idempotency_key: str,
        description: Optional[str] = "Funds Deposit",
    ) -> Transaction:
        """
        Deposits funds into an account and creates corresponding ledger entries.
        """
        if amount <= Decimal("0.00"):
            raise ValueError("Deposit amount must be strictly positive.")

        account = await AccountService.get_account(db, account_id, for_update=True)
        new_balance = account.balance + amount
        account.balance = new_balance
        account.version += 1

        tx = Transaction(
            id=uuid.uuid4(),
            idempotency_key=idempotency_key,
            destination_account_id=account.id,
            amount=amount,
            status=TransactionStatus.COMMITTED,
            description=description,
        )
        db.add(tx)
        await db.flush()

        posting = Posting(
            transaction_id=tx.id,
            account_id=account.id,
            direction=PostingDirection.CREDIT,
            amount=amount,
            balance_after=new_balance,
            sequence_num=0,
        )
        db.add(posting)

        outbox = OutboxEvent(
            aggregate_type="TRANSACTION",
            aggregate_id=tx.id,
            event_type="FUNDS_DEPOSITED",
            payload={
                "transaction_id": str(tx.id),
                "account_id": str(account.id),
                "amount": str(amount),
                "balance_after": str(new_balance),
            },
            status=OutboxStatus.PENDING,
            transaction_id=tx.id,
        )
        db.add(outbox)
        await db.flush()

        return tx
