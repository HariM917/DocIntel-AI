"""Celery application factory (Phase 2).

Broker/result backend are configured exclusively from environment variables
(``REDIS_URL``); no credentials are ever hard-coded.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "docintel",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Deliver a task to one worker at a time and only acknowledge it after the
    # job completes, so a crashed worker does not silently lose work.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=settings.PROCESSING_TASK_TIME_LIMIT,
    task_soft_time_limit=max(60, settings.PROCESSING_TASK_TIME_LIMIT - 60),
    broker_connection_retry_on_startup=True,
)
