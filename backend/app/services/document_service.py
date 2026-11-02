import os
import re
import time
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import UploadFile, HTTPException

from app.config import settings, UPLOAD_DIR
from app.database import db
from app.utils.security import authorization_filter
from app.services.ocr_service import ocr_service
from app.services.document_classifier import document_classifier
from app.services.ner_service import ner_service
from app.services.pii_service import pii_service
from app.services.redaction_service import redaction_service
from app.services.structured_extraction import structured_extraction_service
from app.services.rag_service import rag_service

logger = logging.getLogger("docintel.pipeline")

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks


def sanitize_filename(filename: Optional[str]) -> str:
    """Returns a safe basename derived from an untrusted client filename.

    Strips directory components (both / and \\), path traversal sequences and
    any characters that are not part of a conservative allow-list.
    """
    name = (filename or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._\- ]", "_", name).strip().strip(".")
    name = name.lstrip(".")
    return name or "upload"


def resolve_within(base_dir: Path, candidate: str) -> Optional[Path]:
    """Resolves ``candidate`` and ensures it stays inside ``base_dir``.

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


class DocumentService:
    """Master document processing orchestrator executing the end-to-end intelligence pipeline."""

    async def get_active_security_rules(self) -> Dict[str, bool]:
        """Fetches active security rules map from database (e.g. {'AADHAAR': True, 'PAN': True})."""
        rules_cursor = db.security_rules.find({})
        rules_list = await rules_cursor.to_list(length=100)
        if not rules_list:
            # Default active rules
            return {
                "AADHAAR": True,
                "PAN": True,
                "EMAIL": True,
                "PHONE": True,
                "BANK_ACCOUNT": True,
                "CREDIT_CARD": True,
                "PERSON": False,  # Optional masking for person names
            }
        return {r["entity_type"]: r.get("enabled", True) for r in rules_list}

    async def _store_upload(self, file: UploadFile, save_path: Path, max_bytes: int) -> int:
        """Streams an upload to disk, aborting as soon as the size limit is exceeded."""
        written = 0
        stream = getattr(file, "file", None)
        try:
            with open(save_path, "wb") as buffer:
                while True:
                    chunk = stream.read(_UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=400,
                            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
                        )
                    buffer.write(chunk)
        except HTTPException:
            save_path.unlink(missing_ok=True)
            raise
        except Exception:
            save_path.unlink(missing_ok=True)
            raise
        return written

    async def process_document_file(
        self,
        file: UploadFile,
        current_user_email: Optional[str] = None,
        owner_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes the full 12-step processing pipeline on an uploaded document."""
        # 1. Validation — never trust the client-provided filename.
        safe_name = sanitize_filename(file.filename)
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        content_type = (getattr(file, "content_type", "") or "").split(";")[0].strip().lower()
        if content_type and content_type not in ("application/octet-stream",) and content_type not in settings.ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported file content type")

        # Generate unique document ID (e.g. DOC-A7F92)
        unique_suffix = uuid.uuid4().hex[:6].upper()
        document_id = f"DOC-{unique_suffix}"
        # Storage filename is fully generated (document_id + validated extension);
        # the client filename is never used as a filesystem path.
        storage_name = f"{document_id}{ext}"
        save_path = UPLOAD_DIR / storage_name

        if resolve_within(UPLOAD_DIR, str(save_path)) is None:
            raise HTTPException(status_code=400, detail="Invalid storage path")

        # Measure timing for each step
        pipeline_steps = []
        overall_start = time.perf_counter()

        # Step 1: File Storage (streamed with size enforcement)
        step1_start = time.perf_counter()
        try:
            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            file_size = await self._store_upload(file, save_path, max_bytes)
        except HTTPException:
            raise
        except Exception:
            logger.error("Error saving uploaded file.")
            raise HTTPException(status_code=500, detail="Failed to store uploaded file")

        pipeline_steps.append({
            "name": "UPLOAD",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step1_start) * 1000, 1),
            "details": f"Stored {file_size} bytes as {storage_name}",
        })

        # Step 2: OCR
        step2_start = time.perf_counter()
        ocr_result = ocr_service.process_document(save_path)
        raw_text = ocr_result.get("text", "")
        ocr_conf = ocr_result.get("confidence", 0.85)

        pipeline_steps.append({
            "name": "OCR",
            "status": "completed" if raw_text else "warning",
            "duration_ms": round((time.perf_counter() - step2_start) * 1000, 1),
            "details": f"Extracted {len(raw_text)} characters across {ocr_result.get('pages', 1)} page(s) (conf: {ocr_conf:.2f})",
        })

        # Step 3: Document Classification
        step3_start = time.perf_counter()
        classification = document_classifier.classify(raw_text)
        doc_type = classification.get("document_type", "Other")
        class_conf = classification.get("confidence", 0.75)

        pipeline_steps.append({
            "name": "CLASSIFICATION",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step3_start) * 1000, 1),
            "details": f"Classified as '{doc_type}' with confidence {class_conf:.2f}",
        })

        # Step 4: RoBERTa NER
        step4_start = time.perf_counter()
        entities = ner_service.extract_entities(raw_text)

        pipeline_steps.append({
            "name": "RoBERTa NER",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step4_start) * 1000, 1),
            "details": f"Identified {len(entities)} named entities (Person, Org, Location)",
        })

        # Step 5: PII Detection
        step5_start = time.perf_counter()
        raw_pii_entities = pii_service.detect_pii(raw_text, ner_entities=entities)

        pipeline_steps.append({
            "name": "PII DETECTION",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step5_start) * 1000, 1),
            "details": f"Detected {len(raw_pii_entities)} PII items (Aadhaar, PAN, Emails, Phones, Financial)",
        })

        # Step 6: Validation & Redaction
        step6_start = time.perf_counter()
        active_rules = await self.get_active_security_rules()
        redacted_text, pii_entities = redaction_service.redact_document(raw_text, raw_pii_entities, active_rules)

        pipeline_steps.append({
            "name": "VALIDATION & REDACTION",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step6_start) * 1000, 1),
            "details": f"Masked sensitive items based on {len(active_rules)} active security rules",
        })

        # Step 7: Structured Extraction
        step7_start = time.perf_counter()
        structured_data = structured_extraction_service.extract(doc_type, raw_text, entities, pii_entities)

        pipeline_steps.append({
            "name": "STRUCTURED EXTRACTION",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step7_start) * 1000, 1),
            "details": f"Synthesized typed {doc_type} schema",
        })

        # Step 8: Overall Confidence & Flagging
        # Compute overall confidence from OCR, Classification, and Entity extraction
        conf_scores = [ocr_conf, class_conf]
        if entities:
            conf_scores.append(sum(e["confidence"] for e in entities) / len(entities))
        overall_confidence = round(sum(conf_scores) / len(conf_scores), 4)

        # Flag document if sensitive PII found without verified validity or low confidence
        has_invalid_pii = any(not p.get("valid", True) for p in pii_entities)
        doc_status = "Flagged" if (has_invalid_pii or overall_confidence < 0.65) else "Verified"

        now_iso = datetime.utcnow().isoformat()

        # Step 9: MongoDB Document Storage
        step9_start = time.perf_counter()
        doc_record = {
            "document_id": document_id,
            "filename": safe_name,
            "file_type": ext,
            "file_size": file_size,
            "file_path": str(save_path),
            "document_type": doc_type,
            "classification_confidence": class_conf,
            "status": doc_status,
            "raw_text": raw_text,
            "redacted_text": redacted_text,
            "entities": entities,
            "pii_entities": pii_entities,
            "structured_data": structured_data,
            "confidence": overall_confidence,
            "pipeline_steps": pipeline_steps,
            # Ownership / organization-ready metadata
            "owner": current_user_email or "anonymous",
            "owner_id": owner_id,
            "organization_id": organization_id,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        insert_result = await db.documents.insert_one(doc_record)
        inserted_id = str(insert_result.inserted_id)
        doc_record["id"] = inserted_id
        doc_record["_id"] = inserted_id

        # Step 10: FAISS Vector Indexing
        step10_start = time.perf_counter()
        # Index redacted text so vector search never leaks raw PII
        rag_service.index_document(
            document_id,
            safe_name,
            doc_type,
            redacted_text,
            owner_id=owner_id,
            owner_email=current_user_email,
            organization_id=organization_id,
        )

        pipeline_steps.append({
            "name": "INDEXING & STORAGE",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step10_start) * 1000, 1),
            "details": "Persisted to MongoDB collections and indexed in FAISS vector database",
        })

        # Update document with complete pipeline steps
        await db.documents.update_one(
            {"document_id": document_id},
            {"$set": {"pipeline_steps": pipeline_steps}}
        )

        # Log to processing_logs (metadata only; never document contents)
        await db.processing_logs.insert_one({
            "document_id": document_id,
            "filename": safe_name,
            "owner_id": owner_id,
            "organization_id": organization_id,
            "total_duration_ms": round((time.perf_counter() - overall_start) * 1000, 1),
            "status": doc_status,
            "timestamp": now_iso,
        })

        return doc_record

    async def get_document(self, document_id: str, current_user: dict) -> Optional[Dict[str, Any]]:
        """Fetches a document only if owned by / authorized for the current user."""
        query = {"$and": [{"document_id": document_id}, authorization_filter(current_user)]}
        doc = await db.documents.find_one(query)
        if doc and "_id" in doc:
            doc["id"] = str(doc["_id"])
        return doc

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

    async def delete_document(self, document_id: str, current_user: dict) -> bool:
        query = {"$and": [{"document_id": document_id}, authorization_filter(current_user)]}
        doc = await db.documents.find_one(query)
        if not doc:
            return False

        # Delete local file if present (confined to the upload directory)
        file_path = doc.get("file_path")
        resolved = resolve_within(UPLOAD_DIR, file_path) if file_path else None
        if resolved and resolved.exists():
            try:
                os.remove(resolved)
            except Exception:
                logger.warning("Could not remove stored document file.")

        # Remove from vector index
        rag_service.remove_document(document_id, save=True)

        # Delete from MongoDB (scoped to the authorized document)
        res = await db.documents.delete_one(query)
        return res.deleted_count > 0


document_service = DocumentService()
