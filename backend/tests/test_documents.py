import io
from fastapi.testclient import TestClient
from PIL import Image


def _png_bytes() -> io.BytesIO:
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_document_upload_and_pipeline(client: TestClient, auth_headers):
    headers, _ = auth_headers("uploader")
    buf = _png_bytes()

    # Phase 2: the upload is asynchronous and returns immediately with a job id.
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("test_invoice.png", buf, "image/png")},
    )
    assert res.status_code == 202
    data = res.json()

    assert "document_id" in data
    assert data["document_id"].startswith("DOC-")
    assert data["job_id"].startswith("JOB-")
    assert data["status"] == "queued"

    doc_id = data["document_id"]

    # Processing state is exposed through the protected status endpoint.
    status_res = client.get(f"/api/documents/{doc_id}/status", headers=headers)
    assert status_res.status_code == 200
    status = status_res.json()
    assert status["document_id"] == doc_id
    assert status["status"] in ("queued", "processing", "completed")

    # Retrieve the (now processed) document record.
    get_res = client.get(f"/api/documents/{doc_id}", headers=headers)
    assert get_res.status_code == 200
    doc = get_res.json()
    assert doc["document_id"] == doc_id
    assert "structured_data" in doc
    assert "pipeline_steps" in doc
    # In local (in-process) queue mode the background task has already run.
    assert doc["processing_status"] == "completed"
    assert len(doc["pipeline_steps"]) > 0

    # List documents
    list_res = client.get("/api/documents", headers=headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(d["document_id"] == doc_id for d in list_data["documents"])


def test_document_requires_authentication(client: TestClient):
    buf = _png_bytes()
    res = client.post(
        "/api/documents/process",
        files={"file": ("test_invoice.png", buf, "image/png")},
    )
    assert res.status_code == 401


def test_document_invalid_file_type(client: TestClient, auth_headers):
    headers, _ = auth_headers("badext")
    fake_file = io.BytesIO(b"Hello world executable")
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("test.exe", fake_file, "application/octet-stream")},
    )
    assert res.status_code == 400
