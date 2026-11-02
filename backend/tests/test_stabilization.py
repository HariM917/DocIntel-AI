"""Production-stabilization regression suite (§37).

Implements the 32 mandatory tests from the stabilization specification:

    AUTHORIZATION   1-4     RAG              5-8
    EMBEDDINGS      9-10    CHUNKING        11-12
    CELERY         13-18    CONFIGURATION   19-22
    SECURITY       23-24    DASHBOARD       25
    AI             26-30    STORAGE         31-32

Each test targets a behavior that was corrected or hardened during the
stabilization pass, so a regression in any of them fails the suite.
"""
import asyncio
import hashlib
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.config import Settings, DEV_MONGODB_URI, DEV_REDIS_URL
from app.schemas.dashboard import DashboardStats
from app.services import processing_service
from app.services.authorization_service import (
    can_access_chunk,
    can_access_document,
)
from app.services.document_service import sanitize_filename
from app.services.embedding_service import EmbeddingService, embedding_service
from app.services.ner_service import ner_service
from app.services.processing_service import (
    COMPLETED,
    FAILED,
    PROCESSING,
    PermanentProcessingError,
    TransientProcessingError,
    claim_job,
    create_processing_job,
    execute_document_job,
)
from app.services.quality_service import quality_service
from app.services.rag_service import RAGService
from app.services.redaction_service import redaction_service
from app.services.storage_service import (
    LocalStorageService,
    S3StorageService,
    StorageError,
    build_storage_key,
)
from app.services.validation_service import validation_service


def _png_bytes() -> io.BytesIO:
    img = Image.new("RGB", (200, 150), color=(250, 250, 250))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _upload(client: TestClient, headers: dict, filename: str = "doc.png"):
    return client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": (filename, _png_bytes(), "image/png")},
    )


FAKE_RESULTS = {
    "document_type": "Invoice",
    "classification_confidence": 0.91,
    "status": "Verified",
    "confidence": 0.9,
    "raw_text": "sample raw text",
    "redacted_text": "sample redacted text",
    "entities": [],
    "pii_entities": [],
    "structured_data": {"vendor_name": "ACME"},
    "pipeline_steps": [],
}


@pytest.fixture
def queued_upload(client, auth_headers, monkeypatch):
    """Uploads a document with dispatch suppressed, leaving the job queued."""
    from app.services import document_service as document_service_module

    monkeypatch.setattr(
        document_service_module,
        "enqueue_document_processing",
        lambda *args, **kwargs: "local",
    )

    def _make(prefix: str = "queued"):
        headers, email = auth_headers(prefix)
        res = _upload(client, headers)
        assert res.status_code == 202, res.text
        data = res.json()
        return headers, email, data["document_id"], data["job_id"]

    return _make


def _build_rag_service(metadata, vectors):
    """Builds an in-memory RAGService with a deterministic FAISS index."""
    import faiss

    service = RAGService()
    service._index_loaded = True
    dim = vectors.shape[1]
    service.index = faiss.IndexFlatIP(dim)
    service.index.add(vectors)
    service.metadata = metadata
    return service


# ===========================================================================
# AUTHORIZATION (1-4)
# ===========================================================================

def test_1_unauthenticated_document_access_denied(client: TestClient):
    # Endpoint level: no credentials -> 401 (never touches document storage).
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    # Policy level: a missing user can never access a document.
    assert can_access_document({"owner_id": "u1"}, None) is False
    assert can_access_document({"owner_id": "u1"}, {}) is False


def test_2_user_a_cannot_access_user_b_private_document(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("s2_owner")
    other_headers, _ = auth_headers("s2_intruder")
    doc_id = _upload(client, owner_headers).json()["document_id"]

    assert client.get(f"/api/documents/{doc_id}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/documents/{doc_id}", headers=other_headers).status_code == 404
    # Policy level.
    assert can_access_document({"owner_id": "userA"}, {"user_id": "userB"}) is False


def test_3_different_organization_denied():
    doc = {"owner_id": "u2", "organization_id": "org-1"}
    user = {"user_id": "u9", "organization_id": "org-2"}
    assert can_access_document(doc, user) is False
    # A document without an organization is never shared via the org clause.
    assert can_access_document({"owner_id": "u2"}, {"user_id": "u9", "organization_id": "org-1"}) is False


def test_4_organization_sharing_follows_policy():
    doc = {"owner_id": "u2", "organization_id": "org-1"}
    member = {"user_id": "u9", "organization_id": "org-1"}
    # Same organization -> shared access is granted.
    assert can_access_document(doc, member) is True
    # Primary owner always wins regardless of organization.
    assert can_access_document({"owner_id": "u1", "organization_id": None}, {"user_id": "u1"}) is True
    # A user with no organization cannot match an org-scoped document.
    assert can_access_document(doc, {"user_id": "u9"}) is False


# ===========================================================================
# RAG (5-8)
# ===========================================================================

def test_5_unauthorized_faiss_chunks_never_returned():
    q = embedding_service.embed_query("invoice total amount")
    vector = q.reshape(1, -1).astype(np.float32)
    metadata = [{
        "document_id": "DOC-B", "filename": "b.png", "document_type": "Invoice",
        "text": "invoice total amount", "owner_id": "userB", "organization_id": None,
    }]
    service = _build_rag_service(metadata, vector)

    results = service.search("invoice total amount", top_k=4, owner_id="userA")
    assert results == []


def test_6_top_k_counts_authorized_results():
    q = embedding_service.embed_query("invoice total amount")

    unauthorized = np.repeat((q * 0.99).reshape(1, -1), 12, axis=0).astype(np.float32)
    authorized = np.repeat((q * 0.50).reshape(1, -1), 2, axis=0).astype(np.float32)
    vectors = np.vstack([unauthorized, authorized])

    metadata = []
    for i in range(12):  # higher-ranked but unauthorized
        metadata.append({"document_id": f"DOC-OTHER-{i}", "filename": "o.png",
                         "document_type": "Invoice", "text": "unauthorized",
                         "owner_id": "other", "organization_id": None})
    for i in range(2):  # lower-ranked but authorized
        metadata.append({"document_id": f"DOC-MINE-{i}", "filename": "m.png",
                         "document_type": "Invoice", "text": "authorized",
                         "owner_id": "me", "organization_id": None})

    service = _build_rag_service(metadata, vectors)

    # top_k=2; the initial candidate window (top_k*5=10) contains only
    # unauthorized chunks, so the expanding window must reach the authorized ones.
    results = service.search("invoice total amount", top_k=2, owner_id="me")
    assert len(results) == 2
    assert all(r["document_id"].startswith("DOC-MINE") for r in results)


def test_7_document_id_retrieval_is_authorized():
    q = embedding_service.embed_query("invoice total amount")
    vectors = np.vstack([
        (q * 0.99).reshape(1, -1).astype(np.float32),
        (q * 0.90).reshape(1, -1).astype(np.float32),
    ])
    metadata = [
        {"document_id": "DOC-AUTH", "filename": "a.png", "document_type": "Invoice",
         "text": "authorized content", "owner_id": "me", "organization_id": None},
        {"document_id": "DOC-OTHER", "filename": "o.png", "document_type": "Invoice",
         "text": "other content", "owner_id": "someone-else", "organization_id": None},
    ]
    service = _build_rag_service(metadata, vectors)

    # Authorized document_id resolves; another user's document_id returns nothing.
    mine = service.search("invoice total amount", top_k=2, document_id="DOC-AUTH", owner_id="me")
    assert [r["document_id"] for r in mine] == ["DOC-AUTH"]
    denied = service.search("invoice total amount", top_k=2, document_id="DOC-OTHER", owner_id="me")
    assert denied == []


def test_8_old_or_missing_metadata_handled_safely():
    q = embedding_service.embed_query("legacy chunk")
    vectors = (q * 0.9).reshape(1, -1).astype(np.float32)
    # Legacy chunk: no ownership metadata at all -> must fail closed.
    metadata = [{"document_id": "DOC-LEGACY", "filename": "l.png",
                 "document_type": "Other", "text": "legacy"}]
    service = _build_rag_service(metadata, vectors)

    assert service.search("legacy chunk", top_k=4, owner_id="me") == []
    assert service.search("legacy chunk", top_k=4, owner_email="me@x.com", organization_id="org1") == []
    assert can_access_chunk({}) is False
    assert can_access_chunk({"owner_id": None, "owner": None, "organization_id": None}) is False


# ===========================================================================
# EMBEDDINGS (9-10)
# ===========================================================================

def _fallback_service() -> EmbeddingService:
    svc = EmbeddingService()
    svc._initialized = True
    svc.model = None
    svc._dimension = 384
    svc._backend = "deterministic-fallback"
    return svc


def test_9_fallback_embedding_deterministic():
    svc = _fallback_service()
    v1 = svc.embed_texts(["hello world invoice"])
    v2 = svc.embed_texts(["hello world invoice"])
    assert np.array_equal(v1, v2)

    # A second, independent instance (simulating a new worker process) must
    # produce the identical vector — no Python hash randomization involved.
    svc2 = _fallback_service()
    v3 = svc2.embed_texts(["hello world invoice"])
    assert np.array_equal(v1, v3)

    # Prove the mapping is SHA-256 based rather than the randomized built-in hash.
    expected_idx = int.from_bytes(hashlib.sha256(b"hello").digest()[:8], "big") % 384
    assert v1[0][expected_idx] > 0


def test_10_embedding_dimension_stable():
    svc = _fallback_service()
    vecs = svc.embed_texts(["a", "b", "c"])
    assert vecs.shape == (3, 384)
    assert svc.dimension == 384
    # The configured service dimension must match the fallback dimension so
    # vectors are never mixed across incompatible spaces.
    assert embedding_service.dimension == 384
    assert svc.backend == "deterministic-fallback"
    assert "fallback" in svc.model_version


# ===========================================================================
# CHUNKING (11-12)
# ===========================================================================

def test_11_section_boundaries_correct():
    svc = EmbeddingService()
    text = (
        "INVOICE DETAILS\n\nparagraph alpha one with words\n\nparagraph alpha two with words\n\n"
        "CONTRACT TERMS\n\nparagraph beta one with words"
    )
    chunks = svc.chunk_text(text)

    alpha = [c for c in chunks if "alpha" in c["text"]]
    beta = [c for c in chunks if "beta" in c["text"]]
    assert alpha and beta
    # Section A text carries section A metadata; section B carries section B.
    assert all(c["section"] == "INVOICE DETAILS" for c in alpha)
    assert all(c["section"] == "CONTRACT TERMS" for c in beta)
    # No chunk mixes text from two sections.
    assert not any("alpha" in c["text"] and "beta" in c["text"] for c in chunks)


def test_12_chunking_deterministic():
    svc = EmbeddingService()
    text = (
        "HEADING ONE\n\nfirst paragraph with several words here\n\n"
        "second paragraph also with several words\n\nHEADING TWO\n\nthird paragraph of text"
    )
    assert svc.chunk_text(text) == svc.chunk_text(text)


# ===========================================================================
# CELERY (13-18)
# ===========================================================================

def test_13_celery_task_is_registered():
    from app.worker.celery_app import celery_app
    from app.tasks.document_tasks import process_document_task  # noqa: F401 (registers task)

    assert "docintel.process_document" in celery_app.tasks
    assert process_document_task.name == "docintel.process_document"


def test_14_queued_transitions_to_processing(db_manager):
    job = asyncio.run(create_processing_job("DOC-S14", "owner-1", None))
    assert job["status"] == "queued"
    claimed = asyncio.run(claim_job(job["job_id"]))
    assert claimed is not None and claimed["status"] == PROCESSING


def test_15_processing_transitions_to_completed(client, queued_upload, monkeypatch, db_manager):
    _, _, doc_id, job_id = queued_upload("s15")
    monkeypatch.setattr(processing_service, "_run_pipeline_sync", lambda *a, **k: dict(FAKE_RESULTS))
    monkeypatch.setattr(processing_service.rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(doc_id, job_id, max_attempts=2, backoff=[0], sleep_fn=lambda s: None))

    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == COMPLETED


def test_16_processing_transitions_to_failed(client, queued_upload, monkeypatch, db_manager):
    _, _, doc_id, job_id = queued_upload("s16")

    def boom(*a, **k):
        raise PermanentProcessingError("OCR_FAILED", "Document OCR processing failed.")

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", boom)
    monkeypatch.setattr(processing_service.rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(doc_id, job_id, max_attempts=3, backoff=[0], sleep_fn=lambda s: None))

    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == FAILED
    assert doc["processing_error"]["code"] == "OCR_FAILED"


def test_17_retry_works(client, queued_upload, monkeypatch, db_manager):
    _, _, doc_id, job_id = queued_upload("s17")
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientProcessingError("OCR_FAILED", "temporary")
        return dict(FAKE_RESULTS)

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", flaky)
    monkeypatch.setattr(processing_service.rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(doc_id, job_id, max_attempts=3, backoff=[0], sleep_fn=lambda s: None))

    assert calls["n"] == 2
    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == COMPLETED


def test_18_duplicate_task_does_not_double_process(client, auth_headers, monkeypatch, db_manager):
    # A completed document is never reprocessed, and a second claim is rejected.
    headers, _ = auth_headers("s18")
    doc_id = _upload(client, headers).json()["document_id"]
    assert client.get(f"/api/documents/{doc_id}/status", headers=headers).json()["status"] == COMPLETED

    calls = {"n": 0}

    def should_not_run(*a, **k):
        calls["n"] += 1
        return dict(FAKE_RESULTS)

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", should_not_run)
    monkeypatch.setattr(processing_service.rag_service, "index_document", lambda *a, **k: None)

    job = asyncio.run(create_processing_job(doc_id, "owner-x", None))
    asyncio.run(execute_document_job(doc_id, job["job_id"], max_attempts=2, backoff=[0], sleep_fn=lambda s: None))
    assert calls["n"] == 0

    # Atomic claim: only the first claim succeeds.
    dup = asyncio.run(create_processing_job("DOC-S18-DUP", "owner-1", None))
    assert asyncio.run(claim_job(dup["job_id"])) is not None
    assert asyncio.run(claim_job(dup["job_id"])) is None


# ===========================================================================
# CONFIGURATION (19-22)
# ===========================================================================

def _prod_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        ENVIRONMENT="production",
        JWT_SECRET_KEY="z" * 48,
        CORS_ORIGINS=["https://app.example.com"],
        ALLOW_LOCAL_FALLBACK=False,
        PROCESSING_QUEUE="celery",
        MONGODB_URI="mongodb://mongo.internal:27017",
        REDIS_URL="redis://redis.internal:6379/0",
    )
    base.update(overrides)
    return Settings(**base)


def test_19_production_without_mongodb_fails():
    with pytest.raises(ValidationError):
        _prod_settings(MONGODB_URI=DEV_MONGODB_URI)


def test_20_production_without_jwt_secret_fails():
    with pytest.raises(ValidationError):
        _prod_settings(JWT_SECRET_KEY="short")


def test_21_production_without_redis_fails():
    with pytest.raises(ValidationError):
        _prod_settings(REDIS_URL=DEV_REDIS_URL)


def test_22_production_cannot_use_local_queue():
    with pytest.raises(ValidationError):
        _prod_settings(PROCESSING_QUEUE="local")


# ===========================================================================
# SECURITY (23-24)
# ===========================================================================

def test_23_cors_production_configuration_is_strict():
    with pytest.raises(ValidationError):
        _prod_settings(CORS_ORIGINS=["*"])
    # Explicit origins are accepted.
    assert _prod_settings(CORS_ORIGINS=["https://app.example.com"]).CORS_ORIGINS == [
        "https://app.example.com"
    ]


def test_24_sensitive_data_is_not_logged(client, queued_upload, monkeypatch, db_manager, caplog):
    _, _, doc_id, job_id = queued_upload("s24")
    # Plant a distinctive "sensitive" value on the document; it must never appear in logs.
    asyncio.run(db_manager.documents.update_one(
        {"document_id": doc_id},
        {"$set": {"raw_text": "SECRET-AADHAAR-1234-5678-9012"}},
    ))

    def leak(*a, **k):
        # An unexpected third-party exception whose message contains document content.
        raise RuntimeError("SECRET-AADHAAR-1234-5678-9012 traceback leak")

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", leak)
    monkeypatch.setattr(processing_service.rag_service, "index_document", lambda *a, **k: None)

    with caplog.at_level("DEBUG", logger="docintel"):
        asyncio.run(execute_document_job(doc_id, job_id, max_attempts=1, backoff=[0], sleep_fn=lambda s: None))

    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    # Persisted error is the static safe message — never the raw exception text.
    assert doc["processing_error"]["message"] == "Document processing failed."
    assert "SECRET-AADHAAR" not in str(doc.get("processing_error"))
    # No log record may contain the sensitive value or a stack trace.
    assert "SECRET-AADHAAR" not in caplog.text
    assert "Traceback" not in caplog.text


# ===========================================================================
# DASHBOARD (25)
# ===========================================================================

def test_25_confidence_is_not_presented_as_accuracy(client, auth_headers):
    assert "average_extraction_confidence" in DashboardStats.model_fields
    assert "extraction_accuracy" not in DashboardStats.model_fields

    headers, _ = auth_headers("s25")
    stats = client.get("/api/dashboard/stats", headers=headers).json()
    assert "average_extraction_confidence" in stats
    assert "extraction_accuracy" not in stats


# ===========================================================================
# AI (26-30)
# ===========================================================================

def test_26_ocr_failure_handled(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("ocr engine crash")

    monkeypatch.setattr(processing_service.ocr_service, "process_document", boom)
    with pytest.raises(TransientProcessingError) as exc_info:
        processing_service._run_pipeline_sync(tmp_path / "x.png", "x.png", ".png", {})
    assert exc_info.value.code == "OCR_FAILED"

    # Empty OCR must NOT abort: the pipeline continues in degraded mode.
    monkeypatch.setattr(
        processing_service.ocr_service, "process_document",
        lambda *a, **k: {"text": "", "confidence": 0.0, "pages": 1, "empty": True, "warnings": ["no text"]},
    )
    result = processing_service._run_pipeline_sync(tmp_path / "x.png", "x.png", ".png", {})
    assert result["quality"]["score"] < 0.5
    assert any("OCR" in w or "text" in w.lower() for w in result["processing_warnings"])


def test_27_malformed_entities_rejected():
    text = "Acme Ltd invoice for Rahul Sharma"
    malformed = [
        {"text": "Acme Ltd", "type": "ORGANIZATION", "confidence": 0.9, "start": 0, "end": 8},      # valid
        {"text": "", "type": "PERSON", "confidence": 0.9, "start": 0, "end": 4},                    # empty text
        {"text": "x", "type": "PERSON", "confidence": 0.9, "start": 5, "end": 5},                   # start == end
        {"text": "x", "type": "PERSON", "confidence": 0.9, "start": 4, "end": 3},                   # start > end
        {"text": "x", "type": "PERSON", "confidence": 0.9, "start": 0, "end": 9999},                # out of range
        {"text": "x", "type": "NOT_A_LABEL", "confidence": 0.9, "start": 0, "end": 1},              # bad label
        {"text": "x", "type": "PERSON", "confidence": 5.0, "start": 0, "end": 1},                   # bad confidence
        {"text": "x", "type": "PERSON", "confidence": 0.9, "start": "0", "end": 1},                 # non-int offset
    ]
    valid = ner_service.validate_entities(malformed, text)
    assert len(valid) == 1
    assert valid[0]["text"] == "Acme Ltd"
    # The live extraction path never emits malformed entities either.
    for ent in ner_service.extract_entities(text):
        assert 0 <= ent["start"] < ent["end"] <= len(text)


def test_28_pii_redaction_correct():
    text = "Contact me at jane.doe@example.com or 9876543210."
    entities = [
        {"type": "EMAIL", "value": "jane.doe@example.com", "sensitive": True, "start": 14, "end": 34},
        {"type": "PHONE", "value": "9876543210", "sensitive": True, "start": 38, "end": 48},
    ]
    redacted, processed = redaction_service.redact_document(text, entities, {"EMAIL": True, "PHONE": True})

    assert "jane.doe@example.com" not in redacted
    assert "9876543210" not in redacted
    # Readable masking preserves the domain and the last four phone digits.
    assert "example.com" in redacted
    assert "3210" in redacted
    # Entity order is restored and each carries a masked value.
    assert [e["start"] for e in processed] == [14, 38]
    assert all(e.get("masked_value") for e in processed)


def test_29_validation_works():
    assert validation_service.classify_field("email", "a@b.com") == "valid"
    assert validation_service.classify_field("email", "not-an-email") == "invalid"
    assert validation_service.classify_field("invoice_date", "99/99/9999") == "invalid"
    assert validation_service.classify_field("invoice_date", "15/01/2025") == "valid"
    assert validation_service.classify_field("unknown_field", "anything") == "uncertain"
    assert validation_service.classify_field("email", None) == "uncertain"


def test_30_quality_score_works():
    good = quality_service.assess(
        ocr_confidence=0.95, text_length=1200, entity_count=6,
        structured_data={"vendor_name": "ACME", "total_amount": "100.00"},
        validation_failures=0,
    )
    assert 0.0 <= good["score"] <= 1.0
    assert good["level"] in {"excellent", "good", "fair", "poor"}

    empty = quality_service.assess(
        ocr_confidence=0.0, text_length=0, entity_count=0,
        structured_data={}, validation_failures=0, ocr_empty=True,
    )
    assert empty["score"] < 0.5
    assert empty["level"] == "poor"


# ===========================================================================
# STORAGE (31-32)
# ===========================================================================

def test_31_traversal_blocked(tmp_path):
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert ".." not in build_storage_key("DOC-1", "../../evil.png", "owner", None)

    service = LocalStorageService(tmp_path)
    with pytest.raises(StorageError):
        service.save(io.BytesIO(b"data"), "../escape.txt", 1024)
    assert service.get_path("../escape.txt") is None


def test_32_unsupported_storage_backend_fails_clearly():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, STORAGE_BACKEND="banana")
    # Production refuses S3 (unimplemented) rather than silently using local disk.
    with pytest.raises(ValidationError):
        _prod_settings(STORAGE_BACKEND="s3")
    # The placeholder backend raises a clear error if ever instantiated.
    with pytest.raises(NotImplementedError):
        S3StorageService()
