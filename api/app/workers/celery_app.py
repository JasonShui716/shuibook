from celery import Celery
from celery.schedules import crontab
from app.config import settings


celery_app = Celery(
    "shuibook",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.timezone = settings.timezone
celery_app.conf.beat_schedule = {
    "run-ingest-every-4-hours": {
        "task": "app.workers.tasks.run_ingest_task",
        "schedule": 4 * 60 * 60,
        "args": ("scheduled", None),
    },
    "cleanup-old-items-daily": {
        "task": "app.workers.tasks.cleanup_old_items_task",
        "schedule": crontab(hour=3, minute=10),
    },
}

celery_app.autodiscover_tasks(["app.workers"])
