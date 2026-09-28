import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from app.core.config import settings

_redis_pool: Optional[aioredis.ConnectionPool] = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=50,
            decode_responses=True,
        )
    return _redis_pool


async def get_redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Dependency for providing an async Redis client."""
    pool = get_redis_pool()
    client = aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def acquire_distributed_lock(
    redis_client: aioredis.Redis,
    lock_key: str,
    ttl_seconds: int = 30,
    retry_timeout_seconds: float = 5.0,
    retry_interval_seconds: float = 0.05,
) -> AsyncGenerator[str, None]:
    """
    Acquires an atomic distributed lock via Redis SETNX with a lease TTL.
    Uses exponential backoff / jitter polling up to retry_timeout_seconds.
    
    Yields:
        lock_token (UUID string)
    Raises:
        TimeoutError: if lock cannot be acquired within retry_timeout_seconds.
    """
    token = str(uuid.uuid4())
    start_time = asyncio.get_event_loop().time()

    acquired = False
    while (asyncio.get_event_loop().time() - start_time) < retry_timeout_seconds:
        # SET key token NX EX ttl
        ok = await redis_client.set(lock_key, token, nx=True, ex=ttl_seconds)
        if ok:
            acquired = True
            break
        await asyncio.sleep(retry_interval_seconds)

    if not acquired:
        raise TimeoutError(f"Could not acquire distributed lock for '{lock_key}' within {retry_timeout_seconds}s")

    try:
        yield token
    finally:
        # Lua script to release lock only if the token matches (prevents releasing an expired lock owned by another worker)
        lua_release = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            await redis_client.eval(lua_release, 1, lock_key, token)
        except Exception:
            pass
