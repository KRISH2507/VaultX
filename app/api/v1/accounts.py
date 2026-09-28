import uuid
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from app.core.database import get_db_session
from app.core.redis import get_redis_client
from app.schemas.account import AccountCreate, AccountResponse, AccountBalanceResponse
from app.services.account_service import AccountService, AccountNotFoundError

router = APIRouter(prefix="/accounts", tags=["Accounts"])


class DepositRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0.00"), decimal_places=2)
    description: Optional[str] = Field(default="Account Deposit", max_length=255)


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def create_account(
    data: AccountCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Creates a new financial account in the ledger."""
    account = await AccountService.create_account(db, data)
    await db.commit()
    await db.refresh(account)
    return account


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get account details",
)
async def get_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Fetches details of a specific account."""
    try:
        account = await AccountService.get_account(db, account_id)
        return account
    except AccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{account_id}/balance",
    response_model=AccountBalanceResponse,
    summary="Get account balance",
)
async def get_account_balance(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Fetches real-time settled balance and optimistic lock version for an account."""
    try:
        account = await AccountService.get_account(db, account_id)
        return account
    except AccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/{account_id}/deposit",
    status_code=status.HTTP_201_CREATED,
    summary="Deposit funds into an account",
)
async def deposit_funds(
    account_id: uuid.UUID,
    data: DepositRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db_session),
):
    """Deposits funds into an account and records immutable double-entry line items."""
    key = idempotency_key or str(uuid.uuid4())
    try:
        tx = await AccountService.deposit(
            db=db,
            account_id=account_id,
            amount=data.amount,
            idempotency_key=key,
            description=data.description,
        )
        await db.commit()
        return {
            "status": "success",
            "transaction_id": str(tx.id),
            "account_id": str(account_id),
            "amount": str(data.amount),
        }
    except AccountNotFoundError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
