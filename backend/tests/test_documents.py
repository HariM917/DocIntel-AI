import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import SAMPLE_DOCS_DIR


def test_document_upload_and_pipeline(client: TestClient):
    # Create simple PNG test document
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # Process via API
    res = client.post(
        "/api/documents/process",
        files={"file": ("test_invoice.png", buf, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()

    assert "document_id" in data
    assert data["document_id"].startswith("DOC-")
    assert "status" in data
    assert "structured_data" in data
    assert "pipeline_steps" in data
    assert len(data["pipeline_steps"]) > 0

    doc_id = data["document_id"]

    # Retrieve document
    get_res = client.get(f"/api/documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["document_id"] == doc_id

    # List documents
    list_res = client.get("/api/documents")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(d["document_id"] == doc_id for d in list_data["documents"])


def test_document_invalid_file_type(client: TestClient):
    fake_file = io.BytesIO(b"Hello world executable")
    res = client.post(
        "/api/documents/process",
        files={"file": ("test.exe", fake_file, "application/octet-stream")},
    )
    assert res.status_code == 400
