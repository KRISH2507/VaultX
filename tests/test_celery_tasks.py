from unittest.mock import patch
from app.workers.celery_app import celery_app
from app.workers.tasks import process_outbox_events_task, dispatch_webhook_task


def test_celery_app_configuration():
    assert celery_app.main == "vaultx_workers"
    registered = celery_app.tasks.keys()
    assert "app.workers.tasks.process_outbox_events_task" in registered
    assert "app.workers.tasks.dispatch_webhook_task" in registered


def test_dispatch_webhook_task():
    res = dispatch_webhook_task("https://api.example.com/webhook", {"event": "TRANSACTION_COMMITTED"})
    assert res is True


def test_process_outbox_events_task_execution():
    with patch("app.workers.tasks.OutboxProcessor.process_pending_batch") as mock_process:
        async def mock_coro(*args, **kwargs):
            return {"total": 5, "processed": 5, "failed": 0}

        mock_process.side_effect = mock_coro
        result = process_outbox_events_task(batch_size=20)
        assert result["total"] == 5
        assert result["processed"] == 5
        assert result["failed"] == 0
