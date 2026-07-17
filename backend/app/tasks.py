"""Celery tasks wrapping the processing services."""
from __future__ import annotations

from .celery_app import celery_app
from .database import SessionLocal
from .services import process_media


@celery_app.task(
    name="app.tasks.process_media_task", bind=True, max_retries=2, default_retry_delay=5
)
def process_media_task(self, media_id: str) -> dict:
    """Asynchronously run the anonymization pipeline for a media upload."""
    db = SessionLocal()
    try:
        media = process_media(db, media_id)
        return {"media_id": media_id, "status": media.workflow_status.value}
    except Exception as exc:  # noqa: BLE001
        # process_media already recorded FAILED status; retry transient errors.
        raise self.retry(exc=exc)
    finally:
        db.close()


def enqueue_process_media(media_id: str) -> None:
    """Queue processing. Runs inline when Celery is in eager mode."""
    process_media_task.delay(media_id)
