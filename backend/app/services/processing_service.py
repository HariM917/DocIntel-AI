"""Asynchronous document processing pipeline and job lifecycle (Phase 2/3).

This module owns the OCR -> text-normalization -> structure -> NER -> PII ->
redaction -> structured-extraction -> validation -> quality -> embedding ->
indexing pipeline, relocated so it can run inside a Celery worker (or an
in-process background task) instead of the HTTP request cycle.

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
from app.services.embedding_service import embedding_service
from app.services.text_normalization_service import text_normalization_service
from app.services.structure_service import structure_service
from app.services.quality_service import quality_service
from app.services.validation_service import validation_service
from app.services.pipeline_stages import (
    StageTracker,
    OCR,
    TEXT_NORMALIZATION,
    STRUCTURE_ANALYSIS,
    ENTITY_EXTRACTION,
    PII_DETECTION,
    REDACTION,
    STRUCTURED_EXTRACTION,
    VALIDATION,
    QUALITY_ASSESSMENT,
    INDEXING,
)

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
    """Executes the CPU/IO-bound Phase 3 intelligence pipeline off the event loop.

    Pipeline (Phase 3):
        OCR -> text normalization -> structure detection -> classification ->
        entity extraction -> PII detection -> redaction -> schema-driven
        structured extraction -> field/cross-field validation -> quality
        assessment.

    This is strictly additive: every Phase 1/2 result key is still produced, and
    the Phase 3 keys (``normalized_text``, ``structure``, ``quality``,
    ``validation``, ``processing_metrics``, ``stage_metadata``,
    ``processing_warnings``, ``pipeline_version``) are added alongside them.

    Failure strategy (Step 16): OCR failure aborts the document, but every later
    stage degrades to a recorded warning so one weak component cannot destroy an
    otherwise usable document. Empty OCR is detected and surfaced (warning +
    near-zero quality) rather than blindly treated as a successful extraction.
    """
    tracker = StageTracker()
    metrics: Dict[str, float] = {}
    warnings: List[str] = []
    pipeline_steps: List[Dict[str, Any]] = []

    def _record(record: Dict[str, Any], details: str = "") -> None:
        metrics[record["stage"]] = record["duration_ms"]
        pipeline_steps.append({
            "name": record["stage"],
            "status": record["status"],
            "duration_ms": record["duration_ms"],
            "details": details,
        })

    # --- OCR (critical) ---
    t = tracker.start(OCR)
    try:
        ocr_result = ocr_service.process_document(file_path)
    except Exception as exc:  # OCR engines can fail transiently
        tracker.complete(OCR, t, status="failed", error="OCR_FAILED")
        raise TransientProcessingError("OCR_FAILED", "Document OCR processing failed.") from exc

    raw_text = ocr_result.get("text", "") or ""
    ocr_conf = float(ocr_result.get("confidence", 0.0) or 0.0)
    ocr_pages = int(ocr_result.get("pages", 1) or 0)
    ocr_empty = bool(ocr_result.get("empty", not raw_text.strip()))
    warnings.extend(ocr_result.get("warnings", []) or [])

    if ocr_empty:
        _record(
            tracker.complete(OCR, t, status="warning", error="OCR_EMPTY"),
            "OCR produced no usable text (flagged; pipeline continues in degraded mode).",
        )
    else:
        _record(
            tracker.complete(OCR, t, status="completed"),
            f"Extracted {len(raw_text)} characters across {ocr_pages or 1} page(s) (conf {ocr_conf:.2f})",
        )

    # --- Text normalization (non-critical) ---
    t = tracker.start(TEXT_NORMALIZATION)
    normalized_text = raw_text
    try:
        norm = text_normalization_service.normalize(raw_text)
        normalized_text = norm.get("normalized_text") or raw_text
        warnings.extend(norm.get("warnings", []) or [])
        _record(
            tracker.complete(TEXT_NORMALIZATION, t, status="completed"),
            f"Normalized {len(raw_text)} -> {len(normalized_text)} characters",
        )
    except Exception:
        warnings.append("Text normalization failed; raw OCR text was used instead.")
        _record(tracker.complete(TEXT_NORMALIZATION, t, status="warning", error="NORMALIZATION_FAILED"))

    # Resource guard (Step 18): bound the analysable text length.
    max_text = max(1, int(getattr(settings, "MAX_TEXT_LENGTH", 200000)))
    if len(normalized_text) > max_text:
        normalized_text = normalized_text[:max_text]
        warnings.append(f"Text truncated to MAX_TEXT_LENGTH ({max_text} characters).")

    # --- Structure detection (non-critical) ---
    t = tracker.start(STRUCTURE_ANALYSIS)
    structure: Dict[str, Any] = {}
    try:
        structure = structure_service.analyze(normalized_text)
        _record(
            tracker.complete(STRUCTURE_ANALYSIS, t, status="completed"),
            f"{len(structure.get('headings', []))} heading(s), "
            f"{len(structure.get('key_value_fields', {}))} key-value field(s)",
        )
    except Exception:
        warnings.append("Document structure analysis failed.")
        _record(tracker.complete(STRUCTURE_ANALYSIS, t, status="warning", error="STRUCTURE_FAILED"))

    # --- Classification (kept from Phase 1; a recorded step, not a staged one) ---
    t = time.perf_counter()
    classification = document_classifier.classify(normalized_text)
    doc_type = classification.get("document_type", "Other")
    class_conf = float(classification.get("confidence", 0.75))
    metrics["CLASSIFICATION"] = round((time.perf_counter() - t) * 1000, 1)
    pipeline_steps.append({
        "name": "CLASSIFICATION",
        "status": "completed",
        "duration_ms": metrics["CLASSIFICATION"],
        "details": f"Classified as '{doc_type}' with confidence {class_conf:.2f}",
    })

    # --- Entity extraction (non-critical) ---
    t = tracker.start(ENTITY_EXTRACTION)
    entities: List[Dict[str, Any]] = []
    try:
        entities = ner_service.extract_entities(normalized_text)
        _record(
            tracker.complete(ENTITY_EXTRACTION, t, status="completed"),
            f"Identified {len(entities)} named entity(ies)",
        )
    except Exception:
        warnings.append("Entity extraction failed.")
        _record(tracker.complete(ENTITY_EXTRACTION, t, status="warning", error="NER_FAILED"))

    # --- PII detection (non-critical) ---
    t = tracker.start(PII_DETECTION)
    raw_pii_entities: List[Dict[str, Any]] = []
    try:
        raw_pii_entities = pii_service.detect_pii(normalized_text, ner_entities=entities)
        _record(
            tracker.complete(PII_DETECTION, t, status="completed"),
            f"Detected {len(raw_pii_entities)} PII item(s)",
        )
    except Exception:
        warnings.append("PII detection failed.")
        _record(tracker.complete(PII_DETECTION, t, status="warning", error="PII_FAILED"))

    # --- Redaction (non-critical) ---
    t = tracker.start(REDACTION)
    redacted_text, pii_entities = normalized_text, list(raw_pii_entities)
    try:
        redacted_text, pii_entities = redaction_service.redact_document(
            normalized_text, raw_pii_entities, active_rules
        )
        _record(
            tracker.complete(REDACTION, t, status="completed"),
            f"Masked sensitive items using {len(active_rules)} active security rule(s)",
        )
    except Exception:
        warnings.append("Redaction failed; detected entities were retained unmasked.")
        _record(tracker.complete(REDACTION, t, status="warning", error="REDACTION_FAILED"))

    # --- Schema-driven structured extraction (non-critical) ---
    t = tracker.start(STRUCTURED_EXTRACTION)
    structured_data: Dict[str, Any] = {}
    structured_fields: Dict[str, Any] = {}
    try:
        extraction = structured_extraction_service.extract_with_metadata(
            doc_type, normalized_text, entities, pii_entities
        )
        structured_data = extraction["structured_data"]
        structured_fields = extraction["field_metadata"]
        found = sum(1 for m in structured_fields.values() if m.get("source") not in (None, "not_found", "default"))
        _record(
            tracker.complete(STRUCTURED_EXTRACTION, t, status="completed"),
            f"Synthesized typed {doc_type} schema ({found} field(s) grounded in document evidence)",
        )
    except Exception:
        warnings.append("Structured field extraction failed.")
        _record(tracker.complete(STRUCTURED_EXTRACTION, t, status="warning", error="EXTRACTION_FAILED"))

    # --- Field + cross-field validation (non-critical) ---
    t = tracker.start(VALIDATION)
    field_validation: Dict[str, str] = {}
    cross_field_warnings: List[Dict[str, str]] = []
    validation_failures = 0
    try:
        for field, value in structured_data.items():
            if isinstance(value, (list, dict)):
                continue
            verdict = validation_service.classify_field(field, value)
            field_validation[field] = verdict
            if field in structured_fields:
                structured_fields[field]["validated"] = verdict
            if verdict == "invalid":
                validation_failures += 1
        cross_field_warnings = validation_service.cross_field_validate(doc_type, structured_data)
        _record(
            tracker.complete(VALIDATION, t, status="completed"),
            f"{validation_failures} invalid field(s), {len(cross_field_warnings)} cross-field warning(s)",
        )
    except Exception:
        warnings.append("Field validation failed.")
        _record(tracker.complete(VALIDATION, t, status="warning", error="VALIDATION_FAILED"))

    # --- Quality assessment (non-critical) ---
    t = tracker.start(QUALITY_ASSESSMENT)
    try:
        quality = quality_service.assess(
            ocr_confidence=ocr_conf,
            text_length=len(normalized_text),
            entity_count=len(entities),
            structured_data=structured_data,
            validation_failures=validation_failures,
            ocr_empty=ocr_empty,
            pages=ocr_pages or 1,
        )
        _record(
            tracker.complete(QUALITY_ASSESSMENT, t, status="completed"),
            f"Pipeline quality {quality['score']:.2f} ({quality['level']})",
        )
    except Exception:
        quality = {"score": 0.0, "level": "poor", "issues": ["Quality assessment failed."], "factors": {}}
        warnings.append("Quality assessment failed.")
        _record(tracker.complete(QUALITY_ASSESSMENT, t, status="warning", error="QUALITY_FAILED"))

    # --- Overall confidence & flagging (Phase 1 semantics retained) ---
    conf_scores = [ocr_conf, class_conf]
    if entities:
        conf_scores.append(sum(e["confidence"] for e in entities) / len(entities))
    overall_confidence = round(sum(conf_scores) / len(conf_scores), 4)

    has_invalid_pii = any(not p.get("valid", True) for p in pii_entities)
    validation_status = "Flagged" if (has_invalid_pii or overall_confidence < 0.65) else "Verified"

    # Canonical per-stage duration aliases (§29) alongside the stage-name keys,
    # so consumers can rely on stable metric names.
    metrics.setdefault("ocr_duration_ms", metrics.get("OCR", 0.0))
    metrics.setdefault("ner_duration_ms", metrics.get("ENTITY_EXTRACTION", 0.0))
    metrics.setdefault("pii_duration_ms", metrics.get("PII_DETECTION", 0.0))
    metrics.setdefault("extraction_duration_ms", metrics.get("STRUCTURED_EXTRACTION", 0.0))
    metrics.setdefault("quality_duration_ms", metrics.get("QUALITY_ASSESSMENT", 0.0))

    return {
        # Phase 1/2 keys (unchanged)
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
        # Phase 3 additions (additive)
        "pipeline_version": settings.PIPELINE_VERSION,
        "ner_model_version": getattr(ner_service, "model_name", settings.HF_MODEL_NAME),
        "ocr_model_version": getattr(ocr_service, "engine_version", "pymupdf+tesseract"),
        "embedding_model_version": settings.EMBEDDING_MODEL_VERSION,
        "normalized_text": normalized_text,
        "structure": structure,
        "structured_fields": structured_fields,
        "quality": quality,
        "validation": {
            "fields": field_validation,
            "cross_field_warnings": cross_field_warnings,
            "failures": validation_failures,
        },
        "processing_metrics": metrics,
        "stage_metadata": tracker.summary,
        "processing_warnings": warnings,
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

    # Ensure the Phase 3 metadata containers exist even when a caller supplies a
    # reduced result dict (e.g. the Phase 2 test stub).
    results.setdefault("pipeline_steps", [])
    results.setdefault("processing_metrics", {})
    results.setdefault("processing_warnings", [])
    results.setdefault("structured_fields", {})
    results.setdefault("pipeline_version", settings.PIPELINE_VERSION)
    stage_metadata = results.get("stage_metadata") or {"current_stage": None, "stages": []}
    results["stage_metadata"] = stage_metadata

    # Persist the derived results atomically, but only if the document still
    # exists in `processing`. The lifecycle is deliberately NOT advanced to
    # `completed` here: RAG embedding/indexing (below) is a declared pipeline
    # stage, so `completed` must only be reported once the document is actually
    # retrievable -- otherwise a client that reacts to `completed` can query
    # search/chat before the vector index contains the document.
    now = _now()
    update_result = await db.documents.update_one(
        {"document_id": document_id, "processing_status": PROCESSING},
        {
            "$set": {
                **results,
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
        results.get("document_type", "Other"),
        results.get("redacted_text", ""),
        owner_id,
        owner_email,
        organization_id,
    )
    index_ms = round((time.perf_counter() - index_started) * 1000, 1)

    # Record the embedding/indexing stage (Step 23) and the overall duration.
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    results["processing_metrics"]["INDEXING"] = index_ms
    results["processing_metrics"]["embedding_duration_ms"] = index_ms
    results["processing_metrics"]["TOTAL"] = total_ms
    results["processing_metrics"]["total_processing_duration_ms"] = total_ms
    # Record the embedding model generation actually used (§9/§30).
    results["embedding_model_version"] = embedding_service.model_version
    stage_metadata["stages"].append({
        "stage": INDEXING,
        "status": "completed",
        "started_at": None,
        "completed_at": _now(),
        "duration_ms": index_ms,
        "error": None,
    })
    results["pipeline_steps"].append({
        "name": "INDEXING",
        "status": "completed",
        "duration_ms": index_ms,
        "details": "Chunked, embedded and indexed the redacted text in the FAISS vector store",
    })
    await db.documents.update_one(
        {"document_id": document_id},
        {"$set": {
            "pipeline_steps": results["pipeline_steps"],
            "processing_metrics": results["processing_metrics"],
            "stage_metadata": stage_metadata,
            "embedding_model_version": results.get("embedding_model_version"),
            # The lifecycle is advanced to `completed` only now that the
            # document has been embedded/indexed and is retrievable via RAG.
            "processing_status": COMPLETED,
            "processing_completed_at": _now(),
            "updated_at": _now(),
        }},
    )

    await db.processing_logs.insert_one({
        "document_id": document_id,
        "job_id": job_id,
        "filename": safe_name,
        "owner_id": owner_id,
        "organization_id": organization_id,
        "total_duration_ms": total_ms,
        "status": results.get("status"),
        "pipeline_version": results.get("pipeline_version"),
        "quality_score": (results.get("quality") or {}).get("score"),
        "timestamp": now,
    })

    await _complete_job(document_id, job_id)
    _log_event(
        "document_processing_completed",
        job_id=job_id,
        document_id=document_id,
        operation="process_document",
        status=COMPLETED,
        duration=total_ms,
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
                # §19/§42 — never log the raw exception message or a stack
                # trace here: an unexpected third-party exception could embed
                # document content/PII in its message. Only the exception class
                # name (an internal, non-sensitive identifier) is recorded.
                logger.error(
                    "Unexpected error during document processing (%s).",
                    type(exc).__name__,
                )

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


async def _run_document_processing_async(document_id: str, job_id: str) -> None:
    # A Celery worker process does not execute the FastAPI lifespan, so the
    # shared `db` singleton is never connected there. The API process already
    # connects during startup (and the local/dev background-task path reuses
    # that connection), so only connect when this entrypoint is running in a
    # process that has not yet established a connection.
    from app.database import db

    connected_here = not db.is_connected
    if connected_here:
        await db.connect()
    try:
        await execute_document_job(document_id, job_id)
    finally:
        if connected_here:
            await db.disconnect()


def run_document_processing(document_id: str, job_id: str) -> None:
    """Synchronous entrypoint used by Celery workers and background tasks."""
    asyncio.run(_run_document_processing_async(document_id, job_id))
