import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.outbox import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)

# Type alias for asynchronous event handlers: (payload, event) -> Coroutine
EventHandler = Callable[[Dict[str, Any], OutboxEvent], Coroutine[Any, Any, None]]

_event_handlers: Dict[str, List[EventHandler]] = {}


def register_handler(event_type: str):
    """Decorator to register a consumer callback for a specific Outbox event_type."""
    def decorator(fn: EventHandler):
        if event_type not in _event_handlers:
            _event_handlers[event_type] = []
        _event_handlers[event_type].append(fn)
        return fn
    return decorator


def get_handlers(event_type: str) -> List[EventHandler]:
    """Retrieves all registered handlers for a given event_type."""
    return _event_handlers.get(event_type, [])


class OutboxProcessor:
    """
    High-throughput transactional outbox processor.
    Uses PostgreSQL 'FOR UPDATE SKIP LOCKED' to allow multiple concurrent worker
    processes to poll and process events in parallel without lock collisions or duplicate delivery.
    """
    DEFAULT_BATCH_SIZE = 50
    DEFAULT_MAX_RETRIES = 3

    @staticmethod
    async def fetch_and_claim_batch(
        db: AsyncSession,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> List[OutboxEvent]:
        """
        Fetches up to batch_size PENDING outbox events, claiming row-level locks
        using SKIP LOCKED to avoid blocking concurrent workers.
        """
        bind = db.bind
        dialect_name = bind.dialect.name if bind is not None else "postgresql"

        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size)
        )

        # Use SKIP LOCKED on PostgreSQL; fallback to standard lock/select on SQLite
        if dialect_name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        elif dialect_name != "sqlite":
            stmt = stmt.with_for_update()

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def process_single_event(
        db: AsyncSession,
        event: OutboxEvent,
        max_retries: int = DEFAULT_MAX_RETRIES,
        custom_handler: Optional[EventHandler] = None,
    ) -> bool:
        """
        Executes registered handlers for the given Outbox event and updates its status.
        
        Returns:
            True if successfully processed, False if failed.
        """
        handlers = [custom_handler] if custom_handler else get_handlers(event.event_type)

        try:
            if not handlers:
                # Default handler logs the event if no specific consumer is registered
                logger.info(
                    "Default outbox dispatch: [%s] Aggregate %s: %s",
                    event.event_type,
                    event.aggregate_id,
                    event.payload,
                )
            else:
                for handler in handlers:
                    await handler(event.payload, event)

            # Mark event as PROCESSED
            event.status = OutboxStatus.PROCESSED
            event.processed_at = utc_now()
            await db.flush()
            return True

        except Exception as exc:
            event.retry_count += 1
            logger.warning(
                "Error processing OutboxEvent %s (retry %d/%d): %s",
                event.id,
                event.retry_count,
                max_retries,
                str(exc),
            )

            if event.retry_count >= max_retries:
                event.status = OutboxStatus.FAILED
                event.processed_at = utc_now()
                logger.error(
                    "OutboxEvent %s permanently marked FAILED after %d retries.",
                    event.id,
                    event.retry_count,
                )
            await db.flush()
            return False

    @classmethod
    async def process_pending_batch(
        cls,
        db: AsyncSession,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Dict[str, int]:
        """
        Claims and processes a batch of pending events.
        
        Returns:
            Dictionary with counts of processed, failed, and total events in the batch.
        """
        events = await cls.fetch_and_claim_batch(db, batch_size=batch_size)
        if not events:
            return {"total": 0, "processed": 0, "failed": 0}

        processed_count = 0
        failed_count = 0

        for event in events:
            success = await cls.process_single_event(db, event, max_retries=max_retries)
            if success:
                processed_count += 1
            else:
                failed_count += 1

        await db.commit()
        return {
            "total": len(events),
            "processed": processed_count,
            "failed": failed_count,
        }
