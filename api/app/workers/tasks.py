from app.services.ingest import run_ingest
from app.services.cleanup import cleanup_old_items
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_ingest_task")
def run_ingest_task(
    mode: str = "scheduled",
    run_id: str | None = None,
    source_names: list[str] | None = None,
) -> str:
    return run_ingest(mode=mode, run_id=run_id, source_names=source_names)


@celery_app.task(name="app.workers.tasks.cleanup_old_items_task")
def cleanup_old_items_task() -> int:
    return cleanup_old_items()
