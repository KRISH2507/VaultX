import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey, IdempotencyStatus


class IdempotencyConflictError(Exception):
    """Raised when an operation with the same idempotency key is actively processing."""
    pass


class IdempotencyPayloadMismatchError(Exception):
    """Raised when the same idempotency key is used with a different request payload."""
    pass


def compute_request_hash(payload: Any) -> str:
    """Computes a deterministic SHA-256 hash of a payload dictionary or string."""
    if isinstance(payload, dict):
        serialized = json.dumps(payload, sort_keys=True, default=str)
    else:
        serialized = str(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class IdempotencyManager:
    """
    Two-tier distributed idempotency manager utilizing Redis for millisecond-latency
    locks and PostgreSQL for persistent durable resolution.
    """
    REDIS_KEY_PREFIX = "idempotency:"
    IN_PROGRESS_TTL = 30  # 30-second lock lease
    RESOLVED_TTL = 86400  # 24-hour cache for completed transactions

    @classmethod
    async def check_or_reserve(
        cls,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis],
        idempotency_key: str,
        request_hash: str,
    ) -> Optional[Tuple[int, dict[str, Any]]]:
        """
        Validates the idempotency key:
        - If resolved, returns (response_code, response_body).
        - If actively in progress, raises IdempotencyConflictError.
        - If key was previously used with a different payload, raises IdempotencyPayloadMismatchError.
        - If new, acquires the lock and returns None.
        """
        redis_key = f"{cls.REDIS_KEY_PREFIX}{idempotency_key}"

        # 1. Check Redis (Tier 1)
        if redis_client is not None:
            try:
                cached_raw = await redis_client.get(redis_key)
                if cached_raw:
                    cached_data = json.loads(cached_raw)
                    if cached_data.get("request_hash") != request_hash:
                        raise IdempotencyPayloadMismatchError(
                            f"Idempotency key '{idempotency_key}' was previously used with a different request payload."
                        )
                    if cached_data.get("status") == IdempotencyStatus.IN_PROGRESS.value:
                        raise IdempotencyConflictError(
                            f"Transaction with Idempotency-Key '{idempotency_key}' is currently in progress."
                        )
                    if cached_data.get("status") == IdempotencyStatus.RESOLVED.value:
                        return cached_data.get("response_code", 200), cached_data.get("response_body", {})
            except (IdempotencyConflictError, IdempotencyPayloadMismatchError):
                raise
            except Exception:
                # Redis failure fallback to PostgreSQL
                pass

        # 2. Check Database (Tier 2)
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == idempotency_key)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            if record.request_hash != request_hash:
                raise IdempotencyPayloadMismatchError(
                    f"Idempotency key '{idempotency_key}' was previously used with a different request payload."
                )
            if record.status == IdempotencyStatus.IN_PROGRESS:
                raise IdempotencyConflictError(
                    f"Transaction with Idempotency-Key '{idempotency_key}' is currently in progress."
                )
            if record.status == IdempotencyStatus.RESOLVED:
                # Populate Redis cache if available
                if redis_client is not None:
                    try:
                        resolved_payload = json.dumps({
                            "status": IdempotencyStatus.RESOLVED.value,
                            "request_hash": request_hash,
                            "response_code": record.response_code,
                            "response_body": record.response_body,
                        })
                        await redis_client.set(redis_key, resolved_payload, ex=cls.RESOLVED_TTL)
                    except Exception:
                        pass
                return record.response_code or 200, record.response_body or {}

        # 3. Reserve Lock (Tier 1 Redis SETNX + Tier 2 DB insert)
        if redis_client is not None:
            try:
                lock_payload = json.dumps({
                    "status": IdempotencyStatus.IN_PROGRESS.value,
                    "request_hash": request_hash,
                })
                acquired = await redis_client.set(redis_key, lock_payload, nx=True, ex=cls.IN_PROGRESS_TTL)
                if not acquired:
                    raise IdempotencyConflictError(
                        f"Transaction with Idempotency-Key '{idempotency_key}' is currently in progress."
                    )
            except IdempotencyConflictError:
                raise
            except Exception:
                pass

        # Insert IN_PROGRESS record into DB
        new_record = IdempotencyKey(
            key=idempotency_key,
            request_hash=request_hash,
            status=IdempotencyStatus.IN_PROGRESS,
            locked_until=datetime.now(timezone.utc) + timedelta(seconds=cls.IN_PROGRESS_TTL),
        )
        db.add(new_record)
        await db.flush()

        return None

    @classmethod
    async def resolve(
        cls,
        db: AsyncSession,
        redis_client: Optional[aioredis.Redis],
        idempotency_key: str,
        request_hash: str,
        response_code: int,
        response_body: dict[str, Any],
    ) -> None:
        """
        Marks an idempotency record as RESOLVED in both PostgreSQL and Redis.
        """
        # Update Database
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == idempotency_key)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.status = IdempotencyStatus.RESOLVED
            record.response_code = response_code
            record.response_body = response_body
            record.locked_until = None
            await db.flush()

        # Update Redis
        if redis_client is not None:
            try:
                redis_key = f"{cls.REDIS_KEY_PREFIX}{idempotency_key}"
                resolved_payload = json.dumps({
                    "status": IdempotencyStatus.RESOLVED.value,
                    "request_hash": request_hash,
                    "response_code": response_code,
                    "response_body": response_body,
                })
                await redis_client.set(redis_key, resolved_payload, ex=cls.RESOLVED_TTL)
            except Exception:
                pass
