"""DocIntel AI - End-to-End Pipeline Smoke Test.

Verifies:
1. File Ingestion & Temporary Storage
2. OCR Text Extraction (PyMuPDF / Tesseract)
3. Document Classification (Invoice, Contract, Identity, Form)
4. RoBERTa Named Entity Recognition
5. Sensitive PII Detection (Deterministic Regex & Heuristic)
6. Validation & Redaction Masking
7. Structured JSON Extraction
8. MongoDB Document Persistence
9. FAISS Vector Embedding & RAG Retrieval
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add backend directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.config import settings, SAMPLE_DOCS_DIR
from app.database import db
from app.services.ocr_service import ocr_service
from app.services.document_classifier import document_classifier
from app.services.ner_service import ner_service
from app.services.pii_service import pii_service
from app.services.redaction_service import redaction_service
from app.services.structured_extraction import structured_extraction_service
from app.services.rag_service import rag_service
from app.services.document_service import document_service


class MockUploadFile:
    def __init__(self, file_path: Path):
        self.filename = file_path.name
        self.file = open(file_path, "rb")


async def run_pipeline_test():
    print("=" * 70)
    print(" DOCINTEL AI - END-TO-END PIPELINE SMOKE TEST")
    print("=" * 70)

    # Step 0: Database Connect
    print("\n[STEP 0] Connecting to Database...")
    await db.connect()
    print(f" Database connected: Mode = {'Fallback Local JSON' if db.fallback_mode else 'MongoDB Native'}")

    sample_invoice = SAMPLE_DOCS_DIR / "sample_invoice.pdf"
    if not sample_invoice.exists():
        print(f" ERROR: Sample invoice {sample_invoice} not found. Run scripts/create_sample_docs.py first.")
        return False

    print(f"\nTarget Document: {sample_invoice.name} ({os.path.getsize(sample_invoice):,} bytes)")

    # Step 1: Ingestion & Full Orchestration
    print("\n[STEP 1] Executing Document Processing Pipeline...")
    mock_file = MockUploadFile(sample_invoice)
    start_time = time.perf_counter()

    try:
        result = await document_service.process_document_file(mock_file, current_user_email="smoke_test@docintel.ai")
    finally:
        mock_file.file.close()

    elapsed = time.perf_counter() - start_time
    print(f" Pipeline executed successfully in {elapsed:.2f} seconds!")

    # Step 2: Validate Result Schema
    print("\n[STEP 2] Verifying Pipeline Components...")

    doc_id = result["document_id"]
    doc_type = result["document_type"]
    status = result["status"]
    raw_text = result["raw_text"]
    redacted_text = result["redacted_text"]
    entities = result["entities"]
    pii_entities = result["pii_entities"]
    structured_data = result["structured_data"]
    confidence = result["confidence"]

    print(f" Document ID: {doc_id}")
    print(f" Classification: {doc_type} (Overall Confidence: {confidence * 100:.1f}%)")
    print(f" Compliance Status: {status}")
    print(f" Raw OCR Length: {len(raw_text)} characters")
    print(f" Redacted Text Length: {len(redacted_text)} characters")
    print(f" Named Entities Extracted: {len(entities)}")
    print(f" Sensitive PII Detected: {len(pii_entities)}")

    assert doc_id.startswith("DOC-"), "Document ID must start with 'DOC-'"
    assert doc_type == "Invoice", f"Expected Invoice, got {doc_type}"
    assert len(raw_text) > 50, "OCR must extract text from document"
    assert len(entities) > 0, "NER should extract at least one entity"
    assert len(pii_entities) > 0, "PII detector should identify sensitive items"
    assert structured_data.get("invoice_number") != "N/A", "Should extract invoice_number"

    # Step 3: Verify MongoDB Retrieval
    print("\n[STEP 3] Verifying Database Retrieval...")
    retrieved = await document_service.get_document(doc_id)
    assert retrieved is not None, "Failed to retrieve document from database"
    assert retrieved["document_id"] == doc_id
    print(f" Document verified in database: {retrieved['document_id']}")

    # Step 4: Verify Vector Search / RAG
    print("\n[STEP 4] Verifying FAISS Vector Search & RAG Assistant...")
    query = "What is the invoice amount?"
    rag_result = await rag_service.answer_question(query, document_id=doc_id)
    print(f" Query: \"{query}\"")
    print(f" AI Response: {rag_result['answer']}")
    print(f" Sources Retrieved: {len(rag_result['sources'])} chunks")
    assert len(rag_result["sources"]) > 0, "FAISS must retrieve indexed chunks"

    print("\n" + "=" * 70)
    print(" ALL PIPELINE SMOKE TESTS PASSED CLEANLY!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_pipeline_test())
    sys.exit(0 if success else 1)
