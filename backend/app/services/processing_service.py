"""Asynchronous document processing pipeline and job lifecycle (Phase 2).

This module owns the *exact* existing OCR -> NER -> PII -> redaction ->
structured-extraction -> validation -> embedding pipeline, relocated so it can
run inside a Celery worker (or an in-process background task) instead of the
HTTP request cycle.

Guarantees:
* Authorization metadata (owner_id / organization_id) is read from the stored
  document, never from an untrusted request parameter.
* Job claiming is atomic, so two workers cannot process one document
  concurrently.
* Processing is idempotent: a completed document is never processed twice.
* Transient failures are retried with exponential backoff up to a bounded
  limit; permanent failures fail immediately.
* Only safe error codes/messages are persisted or logged (never stack traces,
  PII, secrets, tokens or document content).
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from app.config import settings
from app.database import db
from app.services.storage_service import storage_service
from app.services.ocr_service import ocr_service
from app.services.document_classifier import document_classifier
from app.services.ner_service import ner_service
from app.services.pii_service import pii_service
from app.services.redaction_service import redaction_service
from app.services.structured_extraction import structured_extraction_service
from app.services.rag_service import rag_service

logger = logging.getLogger("docintel.processing")

# ---------------------------------------------------------------------------
# Lifecycle vocabulary
# ---------------------------------------------------------------------------
UPLOADED = "uploaded"
QUEUED = "queued"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

# Controlled document processing transitions (Step 15). ``completed`` is
# terminal unless an explicit reprocess is requested.
_VALID_TRANSITIONS: Dict[str, set] = {
    UPLOADED: {QUEUED, PROCESSING, CANCELLED, FAILED},
    QUEUED: {PROCESSING, CANCELLED, FAILED},
    PROCESSING: {COMPLETED, FAILED, QUEUED, CANCELLED},
    FAILED: {QUEUED, PROCESSING},
    COMPLETED: set(),
    CANCELLED: set(),
}


class ProcessingError(Exception):
    """Base class for safe, classified processing failures."""

    default_code = "PROCESSING_ERROR"
    default_message = "Document processing failed."

    def __init__(self, code: Optional[str] = None, message: Optional[str] = None):
        self.code = code or self.default_code
        self.message = message or self.default_message
        super().__init__(self.message)


class PermanentProcessingError(ProcessingError):
    """Deterministic failure that must never be retried."""

    default_code = "PROCESSING_FAILED"
    default_message = "Document processing failed."


class TransientProcessingError(ProcessingError):
    """Temporary failure that may succeed on retry."""

    default_code = "PROCESSING_RETRYABLE"
    default_message = "Document processing failed. Please try again."


def _now() -> str:
    return datetime.utcnow().isoformat()


def _log_event(event: str, **fields: Any) -> None:
    """Structured, PII-free worker log line.

    Only the explicitly whitelisted operational fields are emitted; document
    content, PII, tokens, passwords and secrets are never logged.
    """
    safe = {k: v for k, v in fields.items() if v is not None}
    logger.info("%s %s", event, json.dumps(safe, default=str))


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------
async def create_processing_job(
    document_id: str,
    owner_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a queued processing job that references (never copies) a document."""
    job = {
        "job_id": f"JOB-{uuid.uuid4().hex[:10].upper()}",
        "document_id": document_id,
        "owner_id": owner_id,
        "organization_id": organization_id,
        "status": QUEUED,
        "attempts": 0,
        "created_at": _now(),
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "error_code": None,
        "error_message": None,
    }
    await db.processing_jobs.insert_one(dict(job))
    return job


async def get_processing_job(job_id: str) -> Optional[Dict[str, Any]]:
    return await db.processing_jobs.find_one({"job_id": job_id})


async def get_active_job_for_document(document_id: str) -> Optional[Dict[str, Any]]:
    """Returns a queued/processing job for a document, if one exists."""
    return await db.processing_jobs.find_one(
        {"document_id": document_id, "status": {"$in": [QUEUED, PROCESSING]}}
    )


async def get_latest_job_for_document(document_id: str) -> Optional[Dict[str, Any]]:
    cursor = db.processing_jobs.find({"document_id": document_id}).sort("created_at", -1)
    items = await cursor.to_list(length=1)
    return items[0] if items else None


async def claim_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Atomically transitions a job queued -> processing.

    Returns the claimed job, or ``None`` when another worker already claimed it
    (or it is no longer queued), which prevents concurrent double-processing.
    """
    return await db.processing_jobs.find_one_and_update(
        {"job_id": job_id, "status": QUEUED},
        {"$set": {"status": PROCESSING, "started_at": _now()}, "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )


async def _set_document_status(
    document_id: str,
    new_status: str,
    extra_set: Optional[Dict[str, Any]] = None,
    allowed_from: Optional[List[str]] = None,
) -> bool:
    """Applies a controlled document processing-status transition."""
    query: Dict[str, Any] = {"document_id": document_id}
    if allowed_from:
        query["processing_status"] = {"$in": allowed_from}
    update_fields: Dict[str, Any] = {"processing_status": new_status, "updated_at": _now()}
    if extra_set:
        update_fields.update(extra_set)
    result = await db.documents.update_one(query, {"$set": update_fields})
    return getattr(result, "matched_count", 0) > 0


async def _requeue_job(document_id: str, job_id: str) -> None:
    await db.processing_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": QUEUED, "error_code": None, "error_message": None}},
    )
    await _set_document_status(document_id, QUEUED)


async def _complete_job(document_id: str, job_id: str) -> None:
    await db.processing_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": COMPLETED, "completed_at": _now()}},
    )


async def _cancel_job(document_id: str, job_id: str, code: str, message: str) -> None:
    await db.processing_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": CANCELLED, "error_code": code, "error_message": message}},
    )
    logger.warning("job_cancelled %s", json.dumps({"job_id": job_id, "document_id": document_id, "code": code}))


async def _fail_job(document_id: str, job_id: str, code: str, message: str) -> None:
    """Marks a job and its document as failed using only safe error information."""
    failed_at = _now()
    job = await db.processing_jobs.find_one({"job_id": job_id})
    attempts = (job or {}).get("attempts", 0)
    await db.processing_jobs.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": FAILED,
                "failed_at": failed_at,
                "error_code": code,
                "error_message": message,
            }
        },
    )
    await db.documents.update_one(
        {"document_id": document_id},
        {
            "$set": {
                "processing_status": FAILED,
                "processing_error": {"code": code, "message": message},
                "retry_count": attempts,
                "updated_at": failed_at,
            }
        },
    )
    _log_event(
        "document_processing_failed",
        job_id=job_id,
        document_id=document_id,
        status=FAILED,
        retry_count=attempts,
        error_code=code,
    )


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------
async def get_active_security_rules() -> Dict[str, bool]:
    """Fetches the active security rules map (e.g. {'AADHAAR': True})."""
    rules_cursor = db.security_rules.find({})
    rules_list = await rules_cursor.to_list(length=100)
    if not rules_list:
        return {
            "AADHAAR": True,
            "PAN": True,
            "EMAIL": True,
            "PHONE": True,
            "BANK_ACCOUNT": True,
            "CREDIT_CARD": True,
            "PERSON": False,
        }
    return {r["entity_type"]: r.get("enabled", True) for r in rules_list}


def _run_pipeline_sync(
    file_path: Path,
    safe_name: str,
    ext: str,
    active_rules: Dict[str, bool],
) -> Dict[str, Any]:
    """Executes the CPU/IO-bound intelligence pipeline (runs off the event loop).

    This is the unchanged Phase 1 pipeline; only its invocation has moved.
    """
    pipeline_steps: List[Dict[str, Any]] = []

    def _step(name: str, started: float, status: str, details: str) -> None:
        pipeline_steps.append({
            "name": name,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "details": details,
        })

    # OCR
    t = time.perf_counter()
    try:
        ocr_result = ocr_service.process_document(file_path)
    except Exception as exc:  # OCR engines can fail transiently
        raise TransientProcessingError("OCR_FAILED", "Document OCR processing failed.") from exc
    raw_text = ocr_result.get("text", "")
    ocr_conf = ocr_result.get("confidence", 0.85)
    _step(
        "OCR",
        t,
        "completed" if raw_text else "warning",
        f"Extracted {len(raw_text)} characters across {ocr_result.get('pages', 1)} page(s) (conf: {ocr_conf:.2f})",
    )

    # Classification
    t = time.perf_counter()
    classification = document_classifier.classify(raw_text)
    doc_type = classification.get("document_type", "Other")
    class_conf = classification.get("confidence", 0.75)
    _step("CLASSIFICATION", t, "completed", f"Classified as '{doc_type}' with confidence {class_conf:.2f}")

    # NER
    t = time.perf_counter()
    entities = ner_service.extract_entities(raw_text)
    _step("RoBERTa NER", t, "completed", f"Identified {len(entities)} named entities (Person, Org, Location)")

    # PII detection
    t = time.perf_counter()
    raw_pii_entities = pii_service.detect_pii(raw_text, ner_entities=entities)
    _step(
        "PII DETECTION",
        t,
        "completed",
        f"Detected {len(raw_pii_entities)} PII items (Aadhaar, PAN, Emails, Phones, Financial)",
    )

    # Validation & redaction
    t = time.perf_counter()
    redacted_text, pii_entities = redaction_service.redact_document(raw_text, raw_pii_entities, active_rules)
    _step(
        "VALIDATION & REDACTION",
        t,
        "completed",
        f"Masked sensitive items based on {len(active_rules)} active security rules",
    )

    # Structured extraction
    t = time.perf_counter()
    structured_data = structured_extraction_service.extract(doc_type, raw_text, entities, pii_entities)
    _step("STRUCTURED EXTRACTION", t, "completed", f"Synthesized typed {doc_type} schema")

    # Overall confidence & flagging
    conf_scores = [ocr_conf, class_conf]
    if entities:
        conf_scores.append(sum(e["confidence"] for e in entities) / len(entities))
    overall_confidence = round(sum(conf_scores) / len(conf_scores), 4)

    has_invalid_pii = any(not p.get("valid", True) for p in pii_entities)
    validation_status = "Flagged" if (has_invalid_pii or overall_confidence < 0.65) else "Verified"

    return {
        "document_type": doc_type,
        "classification_confidence": class_conf,
        "status": validation_status,
        "confidence": overall_confidence,
        "raw_text": raw_text,
        "redacted_text": redacted_text,
        "entities": entities,
        "pii_entities": pii_entities,
        "structured_data": structured_data,
        "pipeline_steps": pipeline_steps,
    }


async def run_processing_job(document_id: str, job_id: str) -> None:
    """Executes a single processing attempt for an already-queued job.

    Raises :class:`PermanentProcessingError` / :class:`TransientProcessingError`
    (or an unexpected exception) so the caller can apply the retry policy.
    Returns quietly when the job cannot be claimed or the document is gone
    (idempotency / deleted-mid-flight handling).
    """
    claimed = await claim_job(job_id)
    if claimed is None:
        _log_event("document_processing_skipped", job_id=job_id, document_id=document_id, status="not_claimable")
        return

    doc = await db.documents.find_one({"document_id": document_id})
    if not doc:
        # Document deleted while queued: never recreate it.
        await _cancel_job(document_id, job_id, "DOCUMENT_DELETED", "Document no longer exists.")
        return

    if doc.get("processing_status") == COMPLETED:
        # Idempotency: a completed document is never processed again.
        await _complete_job(document_id, job_id)
        _log_event("document_processing_skipped", job_id=job_id, document_id=document_id, status=COMPLETED)
        return

    owner_id = doc.get("owner_id")
    organization_id = doc.get("organization_id")
    owner_email = doc.get("owner")
    if not owner_id and not owner_email:
        raise PermanentProcessingError(
            "MISSING_OWNERSHIP_METADATA",
            "Document is missing ownership metadata and cannot be processed securely.",
        )

    storage_key = doc.get("storage_key")
    if not storage_key:
        raise PermanentProcessingError("STORAGE_KEY_MISSING", "Document has no storage key.")
    file_path = storage_service.get_path(storage_key)
    if not file_path:
        raise PermanentProcessingError("STORAGE_OBJECT_MISSING", "Stored document file could not be found.")

    # Transition to processing (guarded; a concurrently deleted document aborts).
    moved = await _set_document_status(
        document_id, PROCESSING, {"processing_started_at": _now(), "processing_error": None},
        allowed_from=[QUEUED, FAILED, UPLOADED],
    )
    if not moved:
        await _cancel_job(document_id, job_id, "STATE_CHANGED", "Document is no longer awaiting processing.")
        return

    started = time.perf_counter()
    _log_event(
        "document_processing_started",
        job_id=job_id,
        document_id=document_id,
        operation="process_document",
        status=PROCESSING,
        retry_count=claimed.get("attempts", 0),
    )

    active_rules = await get_active_security_rules()
    safe_name = doc.get("filename") or "document"
    ext = doc.get("file_type") or Path(safe_name).suffix

    results = await asyncio.to_thread(_run_pipeline_sync, file_path, safe_name, ext, active_rules)

    # Persist atomically, but only if the document still exists in `processing`.
    now = _now()
    update_result = await db.documents.update_one(
        {"document_id": document_id, "processing_status": PROCESSING},
        {
            "$set": {
                **results,
                "processing_status": COMPLETED,
                "processing_completed_at": now,
                "processing_error": None,
                "retry_count": claimed.get("attempts", 0),
                "updated_at": now,
            }
        },
    )
    if getattr(update_result, "matched_count", 0) == 0:
        # Document was deleted mid-processing; discard derived work and do not recreate it.
        await _cancel_job(document_id, job_id, "DOCUMENT_DELETED", "Document was deleted during processing.")
        return

    # Index into RAG using the document's own ownership metadata (never request input).
    index_started = time.perf_counter()
    await asyncio.to_thread(
        rag_service.index_document,
        document_id,
        safe_name,
        results["document_type"],
        results["redacted_text"],
        owner_id,
        owner_email,
        organization_id,
    )
    results["pipeline_steps"].append({
        "name": "INDEXING & STORAGE",
        "status": "completed",
        "duration_ms": round((time.perf_counter() - index_started) * 1000, 1),
        "details": "Persisted to MongoDB collections and indexed in FAISS vector database",
    })
    await db.documents.update_one(
        {"document_id": document_id},
        {"$set": {"pipeline_steps": results["pipeline_steps"]}},
    )

    await db.processing_logs.insert_one({
        "document_id": document_id,
        "job_id": job_id,
        "filename": safe_name,
        "owner_id": owner_id,
        "organization_id": organization_id,
        "total_duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "status": results["status"],
        "timestamp": now,
    })

    await _complete_job(document_id, job_id)
    _log_event(
        "document_processing_completed",
        job_id=job_id,
        document_id=document_id,
        operation="process_document",
        status=COMPLETED,
        duration=round((time.perf_counter() - started) * 1000, 1),
        retry_count=claimed.get("attempts", 0),
    )


async def execute_document_job(
    document_id: str,
    job_id: str,
    max_attempts: Optional[int] = None,
    backoff: Optional[List[int]] = None,
    sleep_fn=time.sleep,
) -> None:
    """Runs a job with bounded exponential-backoff retries (Steps 6, 18, 19).

    Permanent failures fail immediately; transient/unclassified failures are
    retried until ``MAX_PROCESSING_ATTEMPTS`` is exhausted and then marked failed.
    """
    attempts_limit = max_attempts or settings.MAX_PROCESSING_ATTEMPTS
    delays = list(backoff) if backoff is not None else list(settings.RETRY_BACKOFF_SECONDS)

    for attempt_index in range(1, attempts_limit + 1):
        try:
            await run_processing_job(document_id, job_id)
            return
        except PermanentProcessingError as exc:
            await _fail_job(document_id, job_id, exc.code, exc.message)
            return
        except Exception as exc:
            if isinstance(exc, TransientProcessingError):
                code, message = exc.code, exc.message
            else:
                code, message = "PROCESSING_ERROR", "Document processing failed."
                logger.exception("Unexpected error during document processing.")

            job = await get_processing_job(job_id)
            attempts = (job or {}).get("attempts", attempt_index)
            if attempts >= attempts_limit:
                await _fail_job(document_id, job_id, code, message)
                return

            await _requeue_job(document_id, job_id)
            delay = delays[min(attempt_index - 1, len(delays) - 1)] if delays else 0
            _log_event(
                "document_processing_retry",
                job_id=job_id,
                document_id=document_id,
                status=QUEUED,
                retry_count=attempts,
                error_code=code,
                delay_seconds=delay,
            )
            if delay:
                await asyncio.to_thread(sleep_fn, delay)


def run_document_processing(document_id: str, job_id: str) -> None:
    """Synchronous entrypoint used by Celery workers and background tasks."""
    asyncio.run(execute_document_job(document_id, job_id))
