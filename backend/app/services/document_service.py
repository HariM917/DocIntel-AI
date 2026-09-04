import os
import shutil
import time
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import UploadFile, HTTPException

from app.config import settings, UPLOAD_DIR
from app.database import db
from app.services.ocr_service import ocr_service
from app.services.document_classifier import document_classifier
from app.services.ner_service import ner_service
from app.services.pii_service import pii_service
from app.services.redaction_service import redaction_service
from app.services.structured_extraction import structured_extraction_service
from app.services.rag_service import rag_service

logger = logging.getLogger("docintel.pipeline")


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

    async def process_document_file(self, file: UploadFile, current_user_email: Optional[str] = None) -> Dict[str, Any]:
        """Executes the full 12-step processing pipeline on an uploaded document."""
        # 1. Validation
        ext = Path(file.filename or "").suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{ext}'. Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        # Generate unique document ID (e.g. DOC-A7F92)
        unique_suffix = uuid.uuid4().hex[:6].upper()
        document_id = f"DOC-{unique_suffix}"
        safe_filename = f"{document_id}_{Path(file.filename or 'upload').name}"
        save_path = UPLOAD_DIR / safe_filename

        # Measure timing for each step
        pipeline_steps = []
        overall_start = time.perf_counter()

        # Step 1: File Storage
        step1_start = time.perf_counter()
        try:
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_size = os.path.getsize(save_path)
            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if file_size > max_bytes:
                save_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving uploaded file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

        pipeline_steps.append({
            "name": "UPLOAD",
            "status": "completed",
            "duration_ms": round((time.perf_counter() - step1_start) * 1000, 1),
            "details": f"Stored {file_size} bytes as {safe_filename}",
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
            "filename": file.filename or safe_filename,
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
            "owner": current_user_email or "anonymous",
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
        rag_service.index_document(document_id, file.filename or safe_filename, doc_type, redacted_text)

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

        # Log to processing_logs
        await db.processing_logs.insert_one({
            "document_id": document_id,
            "filename": file.filename,
            "total_duration_ms": round((time.perf_counter() - overall_start) * 1000, 1),
            "status": doc_status,
            "timestamp": now_iso,
        })

        return doc_record

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        doc = await db.documents.find_one({"document_id": document_id})
        if doc and "_id" in doc:
            doc["id"] = str(doc["_id"])
        return doc

    async def list_documents(
        self,
        doc_type: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if doc_type and doc_type != "All":
            query["document_type"] = doc_type
        if status and status != "All":
            query["status"] = status
        if search:
            query["$or"] = [
                {"document_id": {"$regex": search, "$options": "i"}},
                {"filename": {"$regex": search, "$options": "i"}},
                {"raw_text": {"$regex": search, "$options": "i"}},
            ]

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

    async def delete_document(self, document_id: str) -> bool:
        doc = await db.documents.find_one({"document_id": document_id})
        if not doc:
            return False

        # Delete local file if present
        if "file_path" in doc and os.path.exists(doc["file_path"]):
            try:
                os.remove(doc["file_path"])
            except Exception as e:
                logger.warning(f"Could not remove file: {e}")

        # Remove from vector index
        rag_service.remove_document(document_id, save=True)

        # Delete from MongoDB
        res = await db.documents.delete_one({"document_id": document_id})
        return res.deleted_count > 0


document_service = DocumentService()
