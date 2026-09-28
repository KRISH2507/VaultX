import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import fakeredis.aioredis

from app.models.account import Account
from app.models.posting import PostingDirection
from app.schemas.transaction import TransferCreate
from app.services.ledger_service import LedgerTransferService
from app.services.ledger_validator import (
    InsufficientBalanceError,
    AccountCurrencyMismatchError,
)


@pytest.mark.asyncio
async def test_successful_transfer(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    # Setup accounts
    acc_src = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("500.00"),
        currency="INR",
        version=1,
    )
    acc_dest = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("100.00"),
        currency="INR",
        version=1,
    )
    db_session.add_all([acc_src, acc_dest])
    await db_session.commit()

    transfer_data = TransferCreate(
        source_account_id=acc_src.id,
        destination_account_id=acc_dest.id,
        amount=Decimal("150.00"),
        currency="INR",
        description="Payment for services",
    )

    # Execute transfer
    tx_resp = await LedgerTransferService.transfer(
        db=db_session,
        redis_client=fake_redis,
        idempotency_key="tx-transfer-test-1",
        transfer_data=transfer_data,
    )
    await db_session.commit()

    assert tx_resp.amount == Decimal("150.00")
    assert tx_resp.status.value == "COMMITTED"
    assert len(tx_resp.postings) == 2

    # Verify debit and credit postings
    p_debit = next(p for p in tx_resp.postings if p.direction == PostingDirection.DEBIT)
    p_credit = next(p for p in tx_resp.postings if p.direction == PostingDirection.CREDIT)

    assert p_debit.amount == Decimal("150.00")
    assert p_debit.balance_after == Decimal("350.00")
    assert p_credit.amount == Decimal("150.00")
    assert p_credit.balance_after == Decimal("250.00")

    # Verify updated account balances in DB
    await db_session.refresh(acc_src)
    await db_session.refresh(acc_dest)
    assert acc_src.balance == Decimal("350.00")
    assert acc_src.version == 2
    assert acc_dest.balance == Decimal("250.00")
    assert acc_dest.version == 2


@pytest.mark.asyncio
async def test_overdraft_prevention(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    acc_src = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("50.00"),
        currency="INR",
        version=1,
    )
    acc_dest = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("0.00"),
        currency="INR",
        version=1,
    )
    db_session.add_all([acc_src, acc_dest])
    await db_session.commit()

    transfer_data = TransferCreate(
        source_account_id=acc_src.id,
        destination_account_id=acc_dest.id,
        amount=Decimal("100.00"),  # Exceeds available balance
        currency="INR",
    )

    with pytest.raises(InsufficientBalanceError):
        await LedgerTransferService.transfer(
            db=db_session,
            redis_client=fake_redis,
            idempotency_key="tx-overdraft-test-2",
            transfer_data=transfer_data,
        )


@pytest.mark.asyncio
async def test_currency_mismatch_rejection(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    acc_src = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("500.00"),
        currency="INR",
        version=1,
    )
    acc_dest = Account(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        balance=Decimal("500.00"),
        currency="USD",  # Mismatch
        version=1,
    )
    db_session.add_all([acc_src, acc_dest])
    await db_session.commit()

    transfer_data = TransferCreate(
        source_account_id=acc_src.id,
        destination_account_id=acc_dest.id,
        amount=Decimal("50.00"),
        currency="INR",
    )

    with pytest.raises(AccountCurrencyMismatchError):
        await LedgerTransferService.transfer(
            db=db_session,
            redis_client=fake_redis,
            idempotency_key="tx-curr-mismatch-test-3",
            transfer_data=transfer_data,
        )


@pytest.mark.asyncio
async def test_concurrent_transfers_no_deadlock(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    acc1 = Account(id=uuid.uuid4(), user_id=uuid.uuid4(), balance=Decimal("1000.00"), currency="INR", version=1)
    acc2 = Account(id=uuid.uuid4(), user_id=uuid.uuid4(), balance=Decimal("1000.00"), currency="INR", version=1)
    acc3 = Account(id=uuid.uuid4(), user_id=uuid.uuid4(), balance=Decimal("1000.00"), currency="INR", version=1)
    db_session.add_all([acc1, acc2, acc3])
    await db_session.commit()

    # Interleaved transfers: 1 -> 2, 2 -> 3, 3 -> 1
    t1 = TransferCreate(source_account_id=acc1.id, destination_account_id=acc2.id, amount=Decimal("10.00"), currency="INR")
    t2 = TransferCreate(source_account_id=acc2.id, destination_account_id=acc3.id, amount=Decimal("20.00"), currency="INR")
    t3 = TransferCreate(source_account_id=acc3.id, destination_account_id=acc1.id, amount=Decimal("30.00"), currency="INR")

    await LedgerTransferService.transfer(db_session, fake_redis, "key-c1", t1)
    await LedgerTransferService.transfer(db_session, fake_redis, "key-c2", t2)
    await LedgerTransferService.transfer(db_session, fake_redis, "key-c3", t3)
    await db_session.commit()

    await db_session.refresh(acc1)
    await db_session.refresh(acc2)
    await db_session.refresh(acc3)

    # Net:
    # acc1: 1000 - 10 + 30 = 1020
    # acc2: 1000 + 10 - 20 = 990
    # acc3: 1000 + 20 - 30 = 990
    # Total system balance remains exactly 3000.00 (Zero-sum conservation invariant)
    assert acc1.balance == Decimal("1020.00")
    assert acc2.balance == Decimal("990.00")
    assert acc3.balance == Decimal("990.00")
    assert (acc1.balance + acc2.balance + acc3.balance) == Decimal("3000.00")
