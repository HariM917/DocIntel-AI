"""Task dispatch abstraction (Phase 2).

The API never executes the AI pipeline inline. It hands work to *one* of:

* ``celery`` — the Celery task is published to Redis and executed by a worker.
* ``local``  — the job runs as a FastAPI background task in the same process
  (development/testing convenience; no Redis required).

The selected mode comes from ``PROCESSING_QUEUE`` and never changes the
pipeline logic itself.
"""
import asyncio
import logging
from typing import Optional

from fastapi import BackgroundTasks

from app.config import settings

logger = logging.getLogger("docintel.queue")


async def _run_local(document_id: str, job_id: str) -> None:
    # Imported lazily to avoid a hard dependency on Celery/torch at import time.
    from app.services.processing_service import execute_document_job

    await execute_document_job(document_id, job_id)


def enqueue_document_processing(
    document_id: str,
    job_id: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> str:
    """Dispatches a processing job. Returns the dispatch mode actually used."""
    if settings.PROCESSING_QUEUE == "celery":
        from app.tasks.document_tasks import process_document_task

        process_document_task.delay(document_id, job_id)
        logger.info("Enqueued document processing on Celery broker.")
        return "celery"

    if background_tasks is not None:
        background_tasks.add_task(_run_local, document_id, job_id)
        return "local"

    # Called outside a request lifecycle (e.g. a script): schedule/execute directly.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local(document_id, job_id))
    else:
        loop.create_task(_run_local(document_id, job_id))
    return "local"
