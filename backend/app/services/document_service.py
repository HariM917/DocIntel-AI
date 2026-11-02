"""Document upload orchestration, validation, and CRUD (Phase 2).

Uploads are validated, streamed to a pluggable storage backend using a
*generated* storage key, recorded in MongoDB, and handed to an asynchronous
processing job. The HTTP request never runs the AI pipeline.

The heavy pipeline itself now lives in :mod:`app.services.processing_service`.
"""
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile

from app.config import settings, UPLOAD_DIR
from app.database import db
from app.services import processing_service
from app.services.processing_service import (
    QUEUED,
    create_processing_job,
    get_active_job_for_document,
    get_latest_job_for_document,
    execute_document_job,
)
from app.services.queue_service import enqueue_document_processing
from app.services.storage_service import build_storage_key, storage_service, StorageError
from app.utils.security import authorization_filter

logger = logging.getLogger("docintel.documents")

_SNIFF_BYTES = 16


def sanitize_filename(filename: Optional[str]) -> str:
    """Returns a safe basename derived from an untrusted client filename.

    Strips directory components (both / and \\), path traversal sequences and
    any characters that are not part of a conservative allow-list. The result is
    used *only* as display metadata, never as a filesystem path.
    """
    name = (filename or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._\- ]", "_", name).strip().strip(".")
    name = name.lstrip(".")
    return name or "upload"


def resolve_within(base_dir: Path, candidate: str) -> Optional[Path]:
    """Resolves ``candidate`` and ensures it stays inside ``base_dir``.

    Retained for legacy documents that stored an absolute ``file_path``.
    Returns None if the resolved path would escape the base directory.
    """
    if not candidate:
        return None
    base = base_dir.resolve()
    try:
        resolved = Path(candidate).resolve()
    except (OSError, ValueError):
        return None
    if resolved == base or base in resolved.parents:
        return resolved
    return None


def detect_signature(header: bytes) -> Optional[str]:
    """Detects a file type from its magic bytes (never trust the extension alone)."""
    if header.startswith(b"%PDF"):
        return "pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


_EXTENSION_SIGNATURES: Dict[str, set] = {
    ".pdf": {"pdf"},
    ".png": {"png"},
    ".jpg": {"jpeg"},
    ".jpeg": {"jpeg"},
}


class DocumentService:
    """Coordinates upload validation, storage, persistence and job dispatch."""

    # ------------------------------------------------------------------
    # Upload / validation
    # ------------------------------------------------------------------
    def _validate_upload(self, file: UploadFile) -> tuple:
        """Validates extension, MIME type and magic bytes. Returns (safe_name, ext)."""
        safe_name = sanitize_filename(file.filename)
        ext = os.path.splitext(safe_name)[1].lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        content_type = (getattr(file, "content_type", "") or "").split(";")[0].strip().lower()
        if content_type and content_type != "application/octet-stream" and content_type not in settings.ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported file content type")

        # Content sniffing: reject files whose magic bytes do not match the extension.
        stream = getattr(file, "file", None)
        if stream is not None:
            try:
                position = stream.tell()
                header = stream.read(_SNIFF_BYTES)
                stream.seek(position)
            except Exception:
                header = b""
            signature = detect_signature(header or b"")
            expected = _EXTENSION_SIGNATURES.get(ext, set())
            if header and (signature is None or signature not in expected):
                raise HTTPException(
                    status_code=400,
                    detail="File content does not match its declared type.",
                )

        return safe_name, ext

    async def create_upload(
        self,
        file: UploadFile,
        current_user: dict,
        background_tasks=None,
    ) -> Dict[str, Any]:
        """Validates, stores and queues an upload; returns immediately.

        Nothing here executes OCR/NER/PII/redaction/extraction/embedding.
        """
        safe_name, ext = self._validate_upload(file)

        document_id = f"DOC-{uuid.uuid4().hex[:6].upper()}"
        owner_id = str(current_user.get("user_id") or current_user.get("_id") or current_user.get("id") or current_user.get("email"))
        organization_id = current_user.get("organization_id")
        owner_email = current_user.get("email")

        storage_key = build_storage_key(document_id, ext, owner_id, organization_id)
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

        stream = getattr(file, "file", None)
        if stream is None:
            raise HTTPException(status_code=400, detail="Upload stream unavailable.")
        try:
            file_size = storage_service.save(stream, storage_key, max_bytes)
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            logger.error("Failed to store uploaded file.")
            raise HTTPException(status_code=500, detail="Failed to store uploaded file")

        now = datetime.utcnow().isoformat()
        doc_record = {
            "document_id": document_id,
            "filename": safe_name,
            "file_type": ext,
            "file_size": file_size,
            "storage_key": storage_key,
            "file_path": None,
            "document_type": "Other",
            "classification_confidence": 0.0,
            "status": "Pending",
            "processing_status": QUEUED,
            "processing_started_at": None,
            "processing_completed_at": None,
            "processing_error": None,
            "retry_count": 0,
            "raw_text": "",
            "redacted_text": "",
            "entities": [],
            "pii_entities": [],
            "structured_data": {},
            "structured_fields": {},
            "confidence": 0.0,
            "pipeline_steps": [],
            # Phase 3 additive defaults (populated when processing completes).
            "normalized_text": "",
            "structure": {},
            "quality": None,
            "validation": None,
            "processing_metrics": {},
            "stage_metadata": None,
            "processing_warnings": [],
            "pipeline_version": settings.PIPELINE_VERSION,
            "owner": owner_email or "anonymous",
            "owner_id": owner_id,
            "organization_id": organization_id,
            "created_at": now,
            "updated_at": now,
        }

        try:
            insert_result = await db.documents.insert_one(doc_record)
        except Exception:
            # Do not leave an orphaned object behind if persistence fails.
            storage_service.delete(storage_key)
            raise
        doc_record["id"] = str(insert_result.inserted_id)
        doc_record["_id"] = doc_record["id"]

        job = await create_processing_job(document_id, owner_id, organization_id)
        try:
            enqueue_document_processing(document_id, job["job_id"], background_tasks)
        except Exception:
            # Broker unavailable: surface a clean error and mark the job failed
            # rather than leaving a job silently stuck in `queued`.
            logger.error("Failed to enqueue document processing job.")
            await db.processing_jobs.update_one(
                {"job_id": job["job_id"]},
                {"$set": {"status": "failed", "error_code": "ENQUEUE_FAILED",
                          "error_message": "Unable to queue document for processing."}},
            )
            await db.documents.update_one(
                {"document_id": document_id},
                {"$set": {"processing_status": "failed",
                          "processing_error": {"code": "ENQUEUE_FAILED",
                                               "message": "Unable to queue document for processing."}}},
            )
            raise HTTPException(status_code=503, detail="Processing queue unavailable. Please try again later.")

        return {
            "document_id": document_id,
            "job_id": job["job_id"],
            "status": QUEUED,
        }

    async def process_document_file(
        self,
        file: UploadFile,
        current_user_email: Optional[str] = None,
        owner_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronous convenience wrapper (scripts/seeding/tests).

        Creates the document + job and processes it inline, returning the final
        document record. The HTTP API does NOT use this path.
        """
        current_user = {
            "email": current_user_email or "anonymous",
            "user_id": owner_id,
            "organization_id": organization_id,
        }
        upload = await self.create_upload(file, current_user)
        await execute_document_job(upload["document_id"], upload["job_id"])
        doc = await db.documents.find_one({"document_id": upload["document_id"]})
        if doc and "_id" in doc:
            doc["id"] = str(doc["_id"])
        return doc

    # ------------------------------------------------------------------
    # Retrieval (always authorization-scoped)
    # ------------------------------------------------------------------
    async def get_document(self, document_id: str, current_user: dict) -> Optional[Dict[str, Any]]:
        """Fetches a document only if owned by / authorized for the current user."""
        query = {"$and": [{"document_id": document_id}, authorization_filter(current_user)]}
        doc = await db.documents.find_one(query)
        if doc and "_id" in doc:
            doc["id"] = str(doc["_id"])
        return doc

    async def get_document_status(self, document_id: str, current_user: dict) -> Optional[Dict[str, Any]]:
        """Returns a safe processing-status view for an authorized document."""
        doc = await self.get_document(document_id, current_user)
        if not doc:
            return None

        job = await get_latest_job_for_document(document_id)
        status = doc.get("processing_status", "uploaded")
        progress_map = {"uploaded": 5, "queued": 15, "processing": 60, "completed": 100, "failed": 100}
        error = doc.get("processing_error")
        return {
            "document_id": document_id,
            "status": status,
            "validation_status": doc.get("status"),
            "progress": progress_map.get(status, 0),
            "attempts": (job or {}).get("attempts", doc.get("retry_count", 0)),
            "error": error if status == "failed" and error else None,
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    async def list_documents(
        self,
        current_user: dict,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        conditions: List[Dict[str, Any]] = [authorization_filter(current_user)]
        if doc_type and doc_type != "All":
            conditions.append({"document_type": doc_type})
        if status and status != "All":
            conditions.append({"status": status})
        if search:
            safe_search = re.escape(search)
            conditions.append({"$or": [
                {"document_id": {"$regex": safe_search, "$options": "i"}},
                {"filename": {"$regex": safe_search, "$options": "i"}},
                {"raw_text": {"$regex": safe_search, "$options": "i"}},
            ]})
        query: Dict[str, Any] = {"$and": conditions}

        total = await db.documents.count_documents(query)
        cursor = db.documents.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
        items = await cursor.to_list(length=limit)

        for item in items:
            if "_id" in item:
                item["id"] = str(item["_id"])

        return {
            "documents": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    # ------------------------------------------------------------------
    # Reprocessing (Step 22)
    # ------------------------------------------------------------------
    async def reprocess_document(self, document_id: str, current_user: dict, background_tasks=None) -> Optional[Dict[str, Any]]:
        """Queues a fresh processing job for an authorized document.

        Returns None when the document does not exist / is not authorized, and
        reuses the active job instead of creating uncontrolled duplicates.
        """
        doc = await self.get_document(document_id, current_user)
        if not doc:
            return None

        existing = await get_active_job_for_document(document_id)
        if existing:
            return {"document_id": document_id, "job_id": existing["job_id"], "status": existing["status"]}

        job = await create_processing_job(
            document_id, doc.get("owner_id"), doc.get("organization_id")
        )
        await db.documents.update_one(
            {"document_id": document_id},
            {"$set": {"processing_status": QUEUED, "processing_error": None, "updated_at": datetime.utcnow().isoformat()}},
        )
        enqueue_document_processing(document_id, job["job_id"], background_tasks)
        return {"document_id": document_id, "job_id": job["job_id"], "status": QUEUED}

    # ------------------------------------------------------------------
    # Deletion (Step 21)
    # ------------------------------------------------------------------
    async def delete_document(self, document_id: str, current_user: dict) -> bool:
        query = {"$and": [{"document_id": document_id}, authorization_filter(current_user)]}
        doc = await db.documents.find_one(query)
        if not doc:
            return False

        # Remove the stored object (generated key, or legacy confined path).
        storage_key = doc.get("storage_key")
        if storage_key:
            storage_service.delete(storage_key)
        legacy_path = doc.get("file_path")
        if legacy_path:
            resolved = resolve_within(UPLOAD_DIR, legacy_path)
            if resolved and resolved.exists():
                try:
                    os.remove(resolved)
                except Exception:
                    logger.warning("Could not remove legacy stored document file.")

        # Remove derived vector data.
        processing_service.rag_service.remove_document(document_id, save=True)

        # Cancel any in-flight job so a worker does not resurrect the record.
        await db.processing_jobs.update_one(
            {"document_id": document_id, "status": {"$in": [QUEUED, "processing"]}},
            {"$set": {"status": "cancelled", "error_code": "DOCUMENT_DELETED",
                      "error_message": "Document was deleted."}},
        )

        res = await db.documents.delete_one(query)
        return res.deleted_count > 0


document_service = DocumentService()
