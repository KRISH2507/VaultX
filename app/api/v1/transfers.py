import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import redis.asyncio as aioredis

from app.core.database import get_db_session
from app.core.metrics import (
    TRANSFERS_TOTAL,
    TRANSFER_DURATION_SECONDS,
    ACTIVE_TRANSFER_LOCKS,
)
from app.core.redis import get_redis_client
from app.models.transaction import Transaction
from app.schemas.transaction import TransferCreate, TransactionResponse, PostingResponse
from app.services.account_service import AccountNotFoundError
from app.services.idempotency import (
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
)
from app.services.ledger_service import LedgerTransferService
from app.services.ledger_validator import (
    InsufficientBalanceError,
    AccountCurrencyMismatchError,
)

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute an ACID double-entry transfer",
)
async def execute_transfer(
    data: TransferCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        description="Unique UUID/string ensuring zero duplicate transfers on network retry storms",
    ),
    db: AsyncSession = Depends(get_db_session),
    redis_client: aioredis.Redis = Depends(get_redis_client),
):
    """
    Transfers balance atomically between two accounts with strict double-entry invariants,
    deadlock-free deterministic lock sequencing, and distributed idempotency.
    """
    start_time = time.perf_counter()
    ACTIVE_TRANSFER_LOCKS.inc()
    try:
        response = await LedgerTransferService.transfer(
            db=db,
            redis_client=redis_client,
            idempotency_key=idempotency_key,
            transfer_data=data,
        )
        await db.commit()
        duration = time.perf_counter() - start_time
        TRANSFER_DURATION_SECONDS.observe(duration)
        TRANSFERS_TOTAL.labels(status="committed").inc()
        return response

    except IdempotencyConflictError as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="conflict").inc()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IdempotencyPayloadMismatchError as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="payload_mismatch").inc()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except InsufficientBalanceError as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="insufficient_balance").inc()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except AccountNotFoundError as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="account_not_found").inc()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AccountCurrencyMismatchError as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="currency_mismatch").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        TRANSFERS_TOTAL.labels(status="error").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal ledger transfer error: {str(e)}",
        )
    finally:
        ACTIVE_TRANSFER_LOCKS.dec()


@router.get(
    "/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get transaction details with postings",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves an immutable transaction and its double-entry postings."""
    stmt = (
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(selectinload(Transaction.postings))
    )
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found.",
        )

    return TransactionResponse(
        id=tx.id,
        idempotency_key=tx.idempotency_key,
        source_account_id=tx.source_account_id,
        destination_account_id=tx.destination_account_id,
        amount=tx.amount,
        status=tx.status,
        description=tx.description,
        created_at=tx.created_at,
        postings=[PostingResponse.model_validate(p) for p in tx.postings],
    )
