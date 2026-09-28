import uuid
from decimal import Decimal
from typing import Any, Optional
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction, TransactionStatus
from app.models.posting import Posting, PostingDirection
from app.models.outbox import OutboxEvent, OutboxStatus
from app.schemas.transaction import TransferCreate, TransactionResponse, PostingResponse
from app.services.account_service import AccountNotFoundError
from app.services.idempotency import (
    IdempotencyManager,
    compute_request_hash,
)
from app.services.ledger_validator import (
    assert_balanced_postings,
    sort_account_ids_for_locking,
    InsufficientBalanceError,
    AccountCurrencyMismatchError,
)


class LedgerTransferService:
    @staticmethod
    async def transfer(
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis],
        idempotency_key: str,
        transfer_data: TransferCreate,
    ) -> TransactionResponse:
        """
        Executes a high-concurrency ACID double-entry transfer.
        Guarantees:
        1. Distributed Idempotency (Zero duplicate execution on retry storms).
        2. Deadlock-free concurrency (Lexicographical row lock acquisition).
        3. Strict non-negative balance enforcement (Zero overdrafts).
        4. Append-only double-entry audit postings (Sum of Debits == Sum of Credits).
        5. Transactional Outbox event generation for asynchronous consumers.
        """
        payload_dict = transfer_data.model_dump(mode="json")
        request_hash = compute_request_hash(payload_dict)

        # 1. Idempotency Check & Lock Reservation
        cached = await IdempotencyManager.check_or_reserve(
            db=db,
            redis_client=redis_client,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if cached is not None:
            _, response_body = cached
            return TransactionResponse.model_validate(response_body)

        src_id = transfer_data.source_account_id
        dest_id = transfer_data.destination_account_id
        amount = transfer_data.amount

        # 2. Deadlock-Free Deterministic Lock Acquisition
        # Ordering account UUIDs lexicographically prevents circular waits across threads
        sorted_account_ids = sort_account_ids_for_locking([src_id, dest_id])
        locked_accounts: dict[uuid.UUID, Account] = {}

        for acc_id in sorted_account_ids:
            stmt = select(Account).where(Account.id == acc_id).with_for_update()
            result = await db.execute(stmt)
            acc = result.scalar_one_or_none()
            if not acc:
                raise AccountNotFoundError(f"Account '{acc_id}' not found.")
            locked_accounts[acc_id] = acc

        src_account = locked_accounts[src_id]
        dest_account = locked_accounts[dest_id]

        # 3. Currency Validation
        if src_account.currency != dest_account.currency:
            raise AccountCurrencyMismatchError(src_account.currency, dest_account.currency)

        # 4. Solvency / Balance Check (Prevent Double-Spending and Overdrafts)
        if src_account.balance < amount:
            raise InsufficientBalanceError(
                account_id=src_account.id,
                current_balance=src_account.balance,
                requested_amount=amount,
            )

        # 5. Mutate Balances
        new_src_balance = src_account.balance - amount
        new_dest_balance = dest_account.balance + amount

        src_account.balance = new_src_balance
        src_account.version += 1

        dest_account.balance = new_dest_balance
        dest_account.version += 1

        # 6. Create Transaction Record
        tx_id = uuid.uuid4()
        transaction = Transaction(
            id=tx_id,
            idempotency_key=idempotency_key,
            source_account_id=src_id,
            destination_account_id=dest_id,
            amount=amount,
            status=TransactionStatus.COMMITTED,
            description=transfer_data.description,
        )
        db.add(transaction)
        await db.flush()

        # 7. Create Double-Entry Postings (Immutable Line Items)
        debit_posting = Posting(
            id=uuid.uuid4(),
            transaction_id=tx_id,
            account_id=src_id,
            direction=PostingDirection.DEBIT,
            amount=amount,
            balance_after=new_src_balance,
            sequence_num=0,
        )
        credit_posting = Posting(
            id=uuid.uuid4(),
            transaction_id=tx_id,
            account_id=dest_id,
            direction=PostingDirection.CREDIT,
            amount=amount,
            balance_after=new_dest_balance,
            sequence_num=1,
        )

        # Invariant Verification
        assert_balanced_postings([debit_posting, credit_posting])

        db.add(debit_posting)
        db.add(credit_posting)

        # 8. Emit Transactional Outbox Event
        outbox_event = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type="TRANSACTION",
            aggregate_id=tx_id,
            event_type="TRANSACTION_COMMITTED",
            payload={
                "transaction_id": str(tx_id),
                "source_account_id": str(src_id),
                "destination_account_id": str(dest_id),
                "amount": str(amount),
                "currency": src_account.currency,
                "idempotency_key": idempotency_key,
            },
            status=OutboxStatus.PENDING,
            transaction_id=tx_id,
        )
        db.add(outbox_event)
        await db.flush()

        # 9. Format Response
        response = TransactionResponse(
            id=tx_id,
            idempotency_key=idempotency_key,
            source_account_id=src_id,
            destination_account_id=dest_id,
            amount=amount,
            status=TransactionStatus.COMMITTED,
            description=transfer_data.description,
            created_at=transaction.created_at,
            postings=[
                PostingResponse.model_validate(debit_posting),
                PostingResponse.model_validate(credit_posting),
            ],
        )

        # 10. Mark Idempotency as RESOLVED
        response_dict = response.model_dump(mode="json")
        await IdempotencyManager.resolve(
            db=db,
            redis_client=redis_client,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_code=201,
            response_body=response_dict,
        )

        return response
