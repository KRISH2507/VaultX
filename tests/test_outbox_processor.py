import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent, OutboxStatus
from app.workers.outbox_processor import (
    OutboxProcessor,
    register_handler,
    _event_handlers,
)


@pytest.fixture(autouse=True)
def clean_handlers():
    """Clear registered handlers before and after each test."""
    _event_handlers.clear()
    yield
    _event_handlers.clear()


@pytest.mark.asyncio
async def test_fetch_and_claim_pending_events(db_session: AsyncSession):
    # Create 3 pending events and 1 already processed event
    ev1 = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=uuid.uuid4(),
        event_type="TRANSACTION_COMMITTED",
        payload={"tx": 1},
        status=OutboxStatus.PENDING,
    )
    ev2 = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=uuid.uuid4(),
        event_type="TRANSACTION_COMMITTED",
        payload={"tx": 2},
        status=OutboxStatus.PENDING,
    )
    ev3_processed = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=uuid.uuid4(),
        event_type="TRANSACTION_COMMITTED",
        payload={"tx": 3},
        status=OutboxStatus.PROCESSED,
    )
    db_session.add_all([ev1, ev2, ev3_processed])
    await db_session.commit()

    # Claim batch with limit 10
    claimed = await OutboxProcessor.fetch_and_claim_batch(db_session, batch_size=10)
    assert len(claimed) == 2
    claimed_ids = {e.id for e in claimed}
    assert ev1.id in claimed_ids
    assert ev2.id in claimed_ids
    assert ev3_processed.id not in claimed_ids


@pytest.mark.asyncio
async def test_successful_outbox_processing_with_handler(db_session: AsyncSession):
    received_events = []

    @register_handler("TEST_EVENT_OK")
    async def sample_handler(payload, event):
        received_events.append((payload, event.id))

    event = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=uuid.uuid4(),
        event_type="TEST_EVENT_OK",
        payload={"order_id": "ORD-12345", "amount": "99.99"},
        status=OutboxStatus.PENDING,
    )
    db_session.add(event)
    await db_session.commit()

    stats = await OutboxProcessor.process_pending_batch(db_session, batch_size=10)
    assert stats["total"] == 1
    assert stats["processed"] == 1
    assert stats["failed"] == 0

    # Verify handler received payload
    assert len(received_events) == 1
    assert received_events[0][0]["order_id"] == "ORD-12345"

    # Verify event state in DB
    await db_session.refresh(event)
    assert event.status == OutboxStatus.PROCESSED
    assert event.processed_at is not None
    assert event.retry_count == 0


@pytest.mark.asyncio
async def test_outbox_retry_and_permanent_failure(db_session: AsyncSession):
    @register_handler("TEST_EVENT_FAIL")
    async def failing_handler(payload, event):
        raise RuntimeError("Downstream webhook destination unavailable (HTTP 503)")

    event = OutboxEvent(
        aggregate_type="TRANSACTION",
        aggregate_id=uuid.uuid4(),
        event_type="TEST_EVENT_FAIL",
        payload={"transfer_id": "TX-999"},
        status=OutboxStatus.PENDING,
        retry_count=0,
    )
    db_session.add(event)
    await db_session.commit()

    # Attempt 1: Should fail and increment retry_count to 1
    stats1 = await OutboxProcessor.process_pending_batch(db_session, batch_size=10, max_retries=3)
    assert stats1["processed"] == 0
    assert stats1["failed"] == 1

    await db_session.refresh(event)
    assert event.retry_count == 1
    assert event.status == OutboxStatus.PENDING  # Still pending because retry_count < max_retries

    # Attempt 2: Increment retry_count to 2
    stats2 = await OutboxProcessor.process_pending_batch(db_session, batch_size=10, max_retries=3)
    assert stats2["failed"] == 1
    await db_session.refresh(event)
    assert event.retry_count == 2
    assert event.status == OutboxStatus.PENDING

    # Attempt 3: Hits max_retries (3) -> Permanently marked FAILED
    stats3 = await OutboxProcessor.process_pending_batch(db_session, batch_size=10, max_retries=3)
    assert stats3["failed"] == 1
    await db_session.refresh(event)
    assert event.retry_count == 3
    assert event.status == OutboxStatus.FAILED
    assert event.processed_at is not None


@pytest.mark.asyncio
async def test_empty_outbox_batch(db_session: AsyncSession):
    stats = await OutboxProcessor.process_pending_batch(db_session, batch_size=50)
    assert stats == {"total": 0, "processed": 0, "failed": 0}
