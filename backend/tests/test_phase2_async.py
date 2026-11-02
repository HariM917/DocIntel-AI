"""Phase 2 — production document ingestion & asynchronous processing tests.

Covers the acceptance surface for Step 27 of the Phase 2 specification:
upload validation, job creation/dispatch, the async processing lifecycle,
retries, idempotency, authorization, storage-key safety and RAG metadata.

These tests never hit a real broker: the local (in-process) queue mode is used,
and dispatch/pipeline boundaries are monkeypatched where determinism is needed.
"""
import asyncio
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.services import document_service as document_service_module
from app.services import processing_service
from app.services.processing_service import (
    QUEUED,
    PROCESSING,
    COMPLETED,
    FAILED,
    PermanentProcessingError,
    TransientProcessingError,
    claim_job,
    create_processing_job,
    execute_document_job,
)
from app.services.rag_service import RAGService, rag_service
from app.services.storage_service import (
    LocalStorageService,
    StorageError,
    build_storage_key,
)


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


# A minimal, schema-complete pipeline result used to stub the heavy pipeline.
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
    """Uploads a document while suppressing dispatch, leaving the job queued.

    Returns a factory ``(headers, email, document_id, job_id)``.
    """
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


# ---------------------------------------------------------------------------
# UPLOAD (1-5)
# ---------------------------------------------------------------------------

def test_authenticated_upload_succeeds(client: TestClient, auth_headers):
    headers, _ = auth_headers("upload_ok")
    res = _upload(client, headers)
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == QUEUED
    assert body["document_id"].startswith("DOC-")
    assert body["job_id"].startswith("JOB-")


def test_unauthenticated_upload_fails(client: TestClient):
    res = _upload(client, {})
    assert res.status_code == 401


def test_oversized_upload_fails(client: TestClient, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
    headers, _ = auth_headers("oversize")
    res = _upload(client, headers)
    assert res.status_code == 400


def test_unsupported_extension_fails(client: TestClient, auth_headers):
    headers, _ = auth_headers("bad_extension")
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("payload.exe", io.BytesIO(b"MZ\x90\x00binary"), "application/octet-stream")},
    )
    assert res.status_code == 400


def test_declared_type_mismatch_rejected(client: TestClient, auth_headers):
    # A file claiming to be a PNG but with non-PNG magic bytes is rejected.
    headers, _ = auth_headers("bad_signature")
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("fake.png", io.BytesIO(b"MZ\x90\x00not-a-real-png"), "image/png")},
    )
    assert res.status_code == 400


def test_unsafe_filename_is_sanitized(client: TestClient, auth_headers, db_manager):
    headers, _ = auth_headers("unsafe_filename")
    res = _upload(client, headers, filename="../../etc/passwd.png")
    assert res.status_code == 202
    doc_id = res.json()["document_id"]

    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["filename"] == "passwd.png"

    record = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    parts = Path(record["storage_key"]).parts
    assert ".." not in parts
    # The original filename is metadata only; it is never a path component.
    assert "passwd" not in record["storage_key"]


# ---------------------------------------------------------------------------
# JOB CREATION (6-9)
# ---------------------------------------------------------------------------

def test_upload_creates_document_and_queued_job(client, queued_upload, db_manager):
    _, _, doc_id, job_id = queued_upload("job_create")

    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc is not None
    assert doc["processing_status"] == QUEUED

    job = asyncio.run(db_manager.processing_jobs.find_one({"job_id": job_id}))
    assert job is not None
    assert job["status"] == QUEUED
    assert job["document_id"] == doc_id
    assert job["attempts"] == 0


def test_celery_task_is_enqueued(monkeypatch):
    from app.services import queue_service
    import app.tasks.document_tasks as document_tasks

    monkeypatch.setattr(settings, "PROCESSING_QUEUE", "celery")
    dispatched = []
    monkeypatch.setattr(
        document_tasks.process_document_task,
        "delay",
        lambda *args, **kwargs: dispatched.append((args, kwargs)),
    )

    mode = queue_service.enqueue_document_processing("DOC-CELERY", "JOB-CELERY")

    assert mode == "celery"
    assert dispatched
    assert dispatched[0][0] == ("DOC-CELERY", "JOB-CELERY")


# ---------------------------------------------------------------------------
# PROCESSING (10-14)
# ---------------------------------------------------------------------------

def test_worker_claims_queued_job_atomically(db_manager):
    job = asyncio.run(create_processing_job("DOC-CLAIM", "owner-1", None))
    assert job["status"] == QUEUED

    claimed = asyncio.run(claim_job(job["job_id"]))
    assert claimed is not None
    assert claimed["status"] == PROCESSING
    assert claimed["attempts"] == 1


def test_successful_pipeline_marks_completed(client: TestClient, auth_headers):
    headers, _ = auth_headers("pipeline_ok")
    res = _upload(client, headers)
    doc_id = res.json()["document_id"]

    status = client.get(f"/api/documents/{doc_id}/status", headers=headers).json()
    assert status["status"] == COMPLETED
    assert status["progress"] == 100

    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["processing_status"] == COMPLETED
    assert doc["processing_error"] is None


def test_pipeline_failure_marks_failed(client, queued_upload, monkeypatch, db_manager):
    headers, _, doc_id, job_id = queued_upload("pipeline_fail")

    def boom(*args, **kwargs):
        raise PermanentProcessingError("OCR_FAILED", "Document OCR processing failed.")

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", boom)
    monkeypatch.setattr(rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(
        doc_id, job_id, max_attempts=3, backoff=[0], sleep_fn=lambda s: None
    ))

    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == FAILED
    assert doc["processing_error"]["code"] == "OCR_FAILED"
    assert "Traceback" not in doc["processing_error"]["message"]

    job = asyncio.run(db_manager.processing_jobs.find_one({"job_id": job_id}))
    assert job["status"] == FAILED

    # The public status endpoint exposes only the safe error, never a stack trace.
    status = client.get(f"/api/documents/{doc_id}/status", headers=headers).json()
    assert status["status"] == FAILED
    assert status["error"]["code"] == "OCR_FAILED"
    assert "Traceback" not in status["error"]["message"]


def test_retry_succeeds_after_transient_failure(client, queued_upload, monkeypatch, db_manager):
    _, _, doc_id, job_id = queued_upload("retry_ok")
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientProcessingError("OCR_FAILED", "temporary OCR failure")
        return dict(FAKE_RESULTS)

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", flaky)
    monkeypatch.setattr(rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(
        doc_id, job_id, max_attempts=3, backoff=[0], sleep_fn=lambda s: None
    ))

    assert calls["n"] == 2
    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == COMPLETED


def test_retry_limit_marks_failed(client, queued_upload, monkeypatch, db_manager):
    _, _, doc_id, job_id = queued_upload("retry_limit")
    calls = {"n": 0}

    def always_fail(*args, **kwargs):
        calls["n"] += 1
        raise TransientProcessingError("OCR_FAILED", "temporary OCR failure")

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", always_fail)
    monkeypatch.setattr(rag_service, "index_document", lambda *a, **k: None)

    asyncio.run(execute_document_job(
        doc_id, job_id, max_attempts=2, backoff=[0], sleep_fn=lambda s: None
    ))

    assert calls["n"] == 2
    doc = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert doc["processing_status"] == FAILED
    assert doc["retry_count"] == 2


# ---------------------------------------------------------------------------
# IDEMPOTENCY (15-16)
# ---------------------------------------------------------------------------

def test_completed_document_is_not_reprocessed(client, auth_headers, monkeypatch, db_manager):
    headers, _ = auth_headers("idempotent")
    res = _upload(client, headers)
    doc_id = res.json()["document_id"]
    assert client.get(f"/api/documents/{doc_id}/status", headers=headers).json()["status"] == COMPLETED

    calls = {"n": 0}

    def should_not_run(*args, **kwargs):
        calls["n"] += 1
        return dict(FAKE_RESULTS)

    monkeypatch.setattr(processing_service, "_run_pipeline_sync", should_not_run)
    monkeypatch.setattr(rag_service, "index_document", lambda *a, **k: None)

    new_job = asyncio.run(create_processing_job(doc_id, "owner-x", None))
    asyncio.run(execute_document_job(
        doc_id, new_job["job_id"], max_attempts=3, backoff=[0], sleep_fn=lambda s: None
    ))

    assert calls["n"] == 0
    job = asyncio.run(db_manager.processing_jobs.find_one({"job_id": new_job["job_id"]}))
    assert job["status"] == COMPLETED


def test_duplicate_job_claim_is_rejected(db_manager):
    job = asyncio.run(create_processing_job("DOC-DUPLICATE", "owner-1", None))
    assert asyncio.run(claim_job(job["job_id"])) is not None
    # A second worker must not be able to process the same document concurrently.
    assert asyncio.run(claim_job(job["job_id"])) is None


# ---------------------------------------------------------------------------
# AUTHORIZATION (17-19)
# ---------------------------------------------------------------------------

def test_cross_user_status_forbidden(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("status_owner")
    other_headers, _ = auth_headers("status_other")
    doc_id = _upload(client, owner_headers).json()["document_id"]

    assert client.get(f"/api/documents/{doc_id}/status", headers=owner_headers).status_code == 200
    assert client.get(f"/api/documents/{doc_id}/status", headers=other_headers).status_code == 404


def test_cross_user_reprocess_forbidden(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("reprocess_owner")
    other_headers, _ = auth_headers("reprocess_other")
    doc_id = _upload(client, owner_headers).json()["document_id"]

    assert client.post(f"/api/documents/{doc_id}/reprocess", headers=other_headers).status_code == 404


def test_cross_user_delete_forbidden(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("delete_owner")
    other_headers, _ = auth_headers("delete_other")
    doc_id = _upload(client, owner_headers).json()["document_id"]

    assert client.delete(f"/api/documents/{doc_id}", headers=other_headers).status_code == 404
    # The owner's document remains intact.
    assert client.get(f"/api/documents/{doc_id}", headers=owner_headers).status_code == 200


def test_reprocess_reuses_active_job(client, queued_upload):
    headers, _, doc_id, job_id = queued_upload("reprocess_reuse")
    second = client.post(f"/api/documents/{doc_id}/reprocess", headers=headers)
    assert second.status_code == 202
    # No uncontrolled duplicate job is created while one is still active.
    assert second.json()["job_id"] == job_id


# ---------------------------------------------------------------------------
# STORAGE (20-22)
# ---------------------------------------------------------------------------

def test_generated_storage_key_is_safe():
    key = build_storage_key("DOC-ABC123", ".pdf", owner_id="../../etc", organization_id=None)
    parts = Path(key).parts
    assert key.startswith("documents/")
    assert ".." not in parts
    assert "DOC-ABC123" in key
    assert key.endswith(".pdf")

    # A non-trivial extension is dropped entirely rather than used verbatim.
    unsafe = build_storage_key("DOC-1", ".p/df")
    assert ".." not in Path(unsafe).parts
    assert unsafe.endswith("DOC-1")


def test_local_storage_blocks_path_traversal(tmp_path):
    service = LocalStorageService(tmp_path)
    assert service.get_path("../../etc/passwd") is None
    assert service.get_path("/etc/passwd") is None
    assert service.exists("../escape.txt") is False

    with pytest.raises(StorageError):
        service.save(io.BytesIO(b"data"), "../escape.txt", 1024)

    assert not (tmp_path.parent / "escape.txt").exists()


def test_authorized_download_retrieves_stored_file(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("download_owner")
    other_headers, _ = auth_headers("download_other")
    doc_id = _upload(client, owner_headers).json()["document_id"]

    download = client.get(f"/api/documents/{doc_id}/download", headers=owner_headers)
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG\r\n\x1a\n")

    assert client.get(f"/api/documents/{doc_id}/download", headers=other_headers).status_code == 404


# ---------------------------------------------------------------------------
# RAG (23-24)
# ---------------------------------------------------------------------------

def test_completed_processing_indexes_authorized_metadata(client, auth_headers, monkeypatch, db_manager):
    captured = {}

    def capture_index(document_id, filename, document_type, text,
                     owner_id=None, owner_email=None, organization_id=None):
        captured.update({
            "document_id": document_id,
            "owner_id": owner_id,
            "owner_email": owner_email,
            "organization_id": organization_id,
        })

    monkeypatch.setattr(rag_service, "index_document", capture_index)

    headers, email = auth_headers("rag_metadata")
    doc_id = _upload(client, headers).json()["document_id"]

    record = asyncio.run(db_manager.documents.find_one({"document_id": doc_id}))
    assert captured.get("document_id") == doc_id
    # The worker indexes the document's own ownership metadata, not request input.
    assert captured.get("owner_id") == record["owner_id"]
    assert captured.get("owner_email") == email
    assert captured.get("organization_id") == record["organization_id"]


def test_rag_authorization_remains_intact():
    service = RAGService()
    # Fail closed: chunks without any ownership metadata are never authorized.
    assert service._is_authorized({}, "u1", "a@x.com", None) is False
    assert service._is_authorized({"owner_id": "u1"}, "u1", None, None) is True
    assert service._is_authorized({"owner": "a@x.com"}, None, "a@x.com", None) is True
    # Organization membership authorizes a chunk owned by a different user.
    assert service._is_authorized(
        {"owner_id": "someone-else", "organization_id": "org1"}, "u9", "z@x.com", "org1"
    ) is True
    # Organization membership also authorizes an org-scoped chunk, matching the
    # centralized document policy (document.organization_id == user.organization_id, §3).
    assert service._is_authorized({"organization_id": "org1"}, "u9", "z@x.com", "org1") is True
    # A caller from a different organization is never authorized.
    assert service._is_authorized({"organization_id": "org1"}, "u9", "z@x.com", "org2") is False
    assert service._is_authorized({"owner_id": "u1", "owner": "a@x.com"}, "u2", "b@x.com", None) is False


def test_rag_search_filters_by_authorization():
    import faiss
    from app.services.embedding_service import embedding_service

    service = RAGService()
    texts = ["invoice total amount is 1000 rupees", "quarterly contract renewal clause"]
    vectors = embedding_service.embed_texts(texts)
    service.index = faiss.IndexFlatIP(vectors.shape[1])
    service.index.add(vectors)
    service.metadata = [
        {
            "document_id": "DOC-A",
            "filename": "a.png",
            "document_type": "Invoice",
            "text": texts[0],
            "owner_id": "userA",
            "owner": "a@x.com",
            "organization_id": None,
        },
        {
            "document_id": "DOC-B",
            "filename": "b.png",
            "document_type": "Contract",
            "text": texts[1],
            "owner_id": "userB",
            "owner": "b@x.com",
            "organization_id": None,
        },
    ]
    service._index_loaded = True

    results_a = service.search("invoice total amount", top_k=5, owner_id="userA", owner_email="a@x.com")
    assert results_a
    assert all(r["document_id"] == "DOC-A" for r in results_a)

    results_b = service.search("invoice total amount", top_k=5, owner_id="userB", owner_email="b@x.com")
    assert all(r["document_id"] == "DOC-B" for r in results_b)

    # Legacy chunks carrying no ownership metadata are never served.
    service.metadata.append({
        "document_id": "DOC-LEGACY",
        "filename": "legacy.png",
        "document_type": "Other",
        "text": "legacy unowned content",
    })
    legacy_hits = service.search("legacy unowned content", top_k=5, owner_id="userA", owner_email="a@x.com")
    assert all(r["document_id"] != "DOC-LEGACY" for r in legacy_hits)


# ---------------------------------------------------------------------------
# FRONTEND / API CONTRACT (25-26)
# ---------------------------------------------------------------------------

def test_upload_returns_without_waiting_for_processing(client, queued_upload):
    headers, _, doc_id, _ = queued_upload("fast_return")

    # The upload was accepted while the pipeline has not run, proving the HTTP
    # request does not wait for AI processing.
    status = client.get(f"/api/documents/{doc_id}/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == QUEUED
    assert body["progress"] < 100


def test_status_endpoint_reports_correct_state(client: TestClient, auth_headers):
    headers, _ = auth_headers("status_state")
    doc_id = _upload(client, headers).json()["document_id"]

    body = client.get(f"/api/documents/{doc_id}/status", headers=headers).json()
    assert body["document_id"] == doc_id
    assert body["status"] == COMPLETED
    assert body["progress"] == 100
    assert body["error"] is None


def test_status_endpoint_requires_authentication(client: TestClient):
    assert client.get("/api/documents/DOC-DOES-NOT-EXIST/status").status_code == 401


def test_processing_health_endpoint_reports_queue_mode(client: TestClient):
    res = client.get("/api/processing/health")
    assert res.status_code == 200
    assert res.json()["queue_mode"] == settings.PROCESSING_QUEUE
