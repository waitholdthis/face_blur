"""Celery application.

Defaults to eager (synchronous, in-process) execution so the stack runs with no
broker. In production set ``CELERY_TASK_ALWAYS_EAGER=false`` and run a real
worker against Redis (see docker-compose.yml).
"""
from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "face_blur",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)
