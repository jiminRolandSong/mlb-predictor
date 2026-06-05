from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "mlb_predictor",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "nightly-ingest-all-players": {
            "task": "tasks.ingest_all_players",
            "schedule": crontab(hour=4, minute=0),  # 매일 새벽 4시 UTC
        },
    },
)
