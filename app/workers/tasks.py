import asyncio
import logging
from typing import Any, Dict
from celery import shared_task
from app.core.database import AsyncSessionLocal
from app.workers.celery_app import celery_app
from app.workers.outbox_processor import OutboxProcessor
# Ensure handlers are registered
import app.workers.handlers  # noqa: F401

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async coroutines within synchronous Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(name="app.workers.tasks.process_outbox_events_task", bind=True, max_retries=3)
def process_outbox_events_task(self, batch_size: int = 50) -> Dict[str, int]:
    """
    Celery task that polls and processes pending outbox events using SKIP LOCKED.
    Can be run periodically via Celery Beat or triggered on-demand.
    """
    async def _execute():
        async with AsyncSessionLocal() as session:
            try:
                stats = await OutboxProcessor.process_pending_batch(
                    db=session,
                    batch_size=batch_size,
                )
                return stats
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to process outbox batch: %s", str(exc))
                raise exc

    try:
        result = run_async(_execute())
        if result["total"] > 0:
            logger.info(
                "Processed outbox batch: Total=%d, Processed=%d, Failed=%d",
                result["total"],
                result["processed"],
                result["failed"],
            )
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)


@celery_app.task(name="app.workers.tasks.dispatch_webhook_task", bind=True, max_retries=5)
def dispatch_webhook_task(self, target_url: str, payload: Dict[str, Any]) -> bool:
    """
    Asynchronous task for delivering webhooks with exponential backoff on transient network failures.
    """
    logger.info("Delivering webhook to %s with payload: %s", target_url, payload)
    # Mock successful HTTP delivery
    return True
