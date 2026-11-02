"""Celery task wrapping the document processing pipeline (Phase 2).

Retry policy, idempotency and atomic job claiming all live in
``app.services.processing_service`` so the same guarantees apply regardless of
how the job was dispatched.
"""
import logging

from app.worker.celery_app import celery_app
from app.services.processing_service import run_document_processing

logger = logging.getLogger("docintel.tasks")


@celery_app.task(name="docintel.process_document", bind=True, acks_late=True)
def process_document_task(self, document_id: str, job_id: str) -> dict:
    """Processes a single document. Ownership metadata is read from the DB,
    never from task arguments, so the task cannot be abused to process another
    user's document."""
    logger.info(
        "Celery task received document processing job.",
        extra={"job_id": job_id, "document_id": document_id},
    )
    run_document_processing(document_id, job_id)
    return {"document_id": document_id, "job_id": job_id, "status": "processed"}
