from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "vaultx_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30,  # 30-second hard limit
    worker_prefetch_multiplier=1,  # Fair distribution
    beat_schedule={
        "process-pending-outbox-events-every-2s": {
            "task": "app.workers.tasks.process_outbox_events_task",
            "schedule": 2.0,  # Poll every 2 seconds
            "args": (50,),
        },
    },
)
