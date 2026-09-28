import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import fakeredis.aioredis

from app.services.idempotency import (
    IdempotencyManager,
    IdempotencyConflictError,
    IdempotencyPayloadMismatchError,
    compute_request_hash,
)


@pytest.mark.asyncio
async def test_idempotency_lifecycle(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    key = "idemp-test-lifecycle-1"
    payload = {"source": "acc-1", "dest": "acc-2", "amount": "100.00"}
    request_hash = compute_request_hash(payload)

    # 1. First attempt -> Lock acquired (returns None)
    res = await IdempotencyManager.check_or_reserve(
        db=db_session,
        redis_client=fake_redis,
        idempotency_key=key,
        request_hash=request_hash,
    )
    assert res is None

    # 2. Concurrent second attempt with SAME key and SAME payload while in progress -> Raises Conflict
    with pytest.raises(IdempotencyConflictError):
        await IdempotencyManager.check_or_reserve(
            db=db_session,
            redis_client=fake_redis,
            idempotency_key=key,
            request_hash=request_hash,
        )

    # 3. Resolve the transaction
    response_body = {"status": "COMMITTED", "tx_id": "abc-123"}
    await IdempotencyManager.resolve(
        db=db_session,
        redis_client=fake_redis,
        idempotency_key=key,
        request_hash=request_hash,
        response_code=201,
        response_body=response_body,
    )

    # 4. Subsequent retry with SAME key and SAME payload -> Returns cached response
    cached = await IdempotencyManager.check_or_reserve(
        db=db_session,
        redis_client=fake_redis,
        idempotency_key=key,
        request_hash=request_hash,
    )
    assert cached is not None
    code, body = cached
    assert code == 201
    assert body == response_body


@pytest.mark.asyncio
async def test_idempotency_payload_mismatch(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis):
    key = "idemp-test-mismatch-2"
    payload_a = {"amount": "100.00"}
    payload_b = {"amount": "999.00"}
    hash_a = compute_request_hash(payload_a)
    hash_b = compute_request_hash(payload_b)

    # Lock with payload A
    await IdempotencyManager.check_or_reserve(
        db=db_session,
        redis_client=fake_redis,
        idempotency_key=key,
        request_hash=hash_a,
    )

    # Attempt with same key but DIFFERENT payload B -> Raises PayloadMismatchError
    with pytest.raises(IdempotencyPayloadMismatchError):
        await IdempotencyManager.check_or_reserve(
            db=db_session,
            redis_client=fake_redis,
            idempotency_key=key,
            request_hash=hash_b,
        )
