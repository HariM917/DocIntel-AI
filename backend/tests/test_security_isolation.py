"""Security, authorization and data-isolation tests for Phase 1 hardening."""
import asyncio
import io
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from PIL import Image

from app.config import Settings, UPLOAD_DIR
from app.services.document_service import sanitize_filename, resolve_within


def _png_bytes() -> io.BytesIO:
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Authentication enforcement
# ---------------------------------------------------------------------------

PROTECTED_GETS = [
    "/api/documents",
    "/api/dashboard/stats",
    "/api/dashboard/recent",
    "/api/search?q=test",
    "/api/security/rules",
]


@pytest.mark.parametrize("path", PROTECTED_GETS)
def test_protected_endpoints_require_token(client: TestClient, path: str):
    res = client.get(path)
    assert res.status_code == 401


def test_invalid_token_rejected(client: TestClient):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


def test_expired_or_malformed_token_rejected(client: TestClient):
    res = client.get("/api/documents", headers={"Authorization": "Bearer a.b.c"})
    assert res.status_code == 401


def test_suspended_account_forbidden(client: TestClient, auth_headers, db_manager):
    headers, email = auth_headers("suspended")

    # Token is valid while the account is active.
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    asyncio.run(db_manager.users.update_one(
        {"email": email}, {"$set": {"status": "suspended"}}
    ))

    forbidden = client.get("/api/auth/me", headers=headers)
    assert forbidden.status_code == 403


def test_registration_never_grants_admin(client: TestClient, auth_headers):
    headers, email = auth_headers("plainuser")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "user"


# ---------------------------------------------------------------------------
# Document isolation between users
# ---------------------------------------------------------------------------

def _upload(client: TestClient, headers: dict) -> str:
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("isolated.png", _png_bytes(), "image/png")},
    )
    # Phase 2: uploads are asynchronous and acknowledged with 202 Accepted.
    assert res.status_code == 202, res.text
    return res.json()["document_id"]


def test_cross_user_document_isolation(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("owner")
    other_headers, _ = auth_headers("intruder")

    doc_id = _upload(client, owner_headers)

    # Owner can access it.
    assert client.get(f"/api/documents/{doc_id}", headers=owner_headers).status_code == 200

    # Another user cannot read, download or delete it (404 never confirms existence).
    assert client.get(f"/api/documents/{doc_id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/download", headers=other_headers).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=other_headers).status_code == 404

    # It must not appear in the other user's listing.
    listing = client.get("/api/documents", headers=other_headers).json()
    assert all(d["document_id"] != doc_id for d in listing["documents"])


def test_search_isolation(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("searchowner")
    other_headers, _ = auth_headers("searchintruder")

    doc_id = _upload(client, owner_headers)

    owner_hits = client.get(f"/api/search?q={doc_id}", headers=owner_headers).json()
    assert any(r["document_id"] == doc_id for r in owner_hits["results"])

    other_hits = client.get(f"/api/search?q={doc_id}", headers=other_headers).json()
    assert all(r["document_id"] != doc_id for r in other_hits["results"])


def test_dashboard_isolation(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("dashowner")
    other_headers, _ = auth_headers("dashintruder")

    _upload(client, owner_headers)

    owner_stats = client.get("/api/dashboard/stats", headers=owner_headers).json()
    other_stats = client.get("/api/dashboard/stats", headers=other_headers).json()

    assert owner_stats["total_processed"] >= 1
    assert other_stats["total_processed"] == 0


def test_chat_cross_user_document_forbidden(client: TestClient, auth_headers):
    owner_headers, _ = auth_headers("chatowner")
    other_headers, _ = auth_headers("chatintruder")

    doc_id = _upload(client, owner_headers)

    res = client.post(
        "/api/chat",
        headers=other_headers,
        json={"message": "summarize", "document_id": doc_id},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Upload / filesystem safety
# ---------------------------------------------------------------------------

def test_sanitize_filename_strips_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert "/" not in sanitize_filename("a/b/c.pdf")
    assert "\\" not in sanitize_filename("..\\..\\windows\\cmd.pdf")


def test_resolve_within_confines_paths():
    assert resolve_within(UPLOAD_DIR, str(UPLOAD_DIR / "doc.png")) is not None
    assert resolve_within(UPLOAD_DIR, os.path.join(str(UPLOAD_DIR), "..", "escape.txt")) is None


# ---------------------------------------------------------------------------
# Production configuration validation
# ---------------------------------------------------------------------------

def test_production_rejects_insecure_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="short",
            CORS_ORIGINS=["https://app.example.com"],
            ALLOW_LOCAL_FALLBACK=False,
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="x" * 48,
            CORS_ORIGINS=["*"],
            ALLOW_LOCAL_FALLBACK=False,
        )


def test_production_rejects_local_fallback():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            JWT_SECRET_KEY="x" * 48,
            CORS_ORIGINS=["https://app.example.com"],
            ALLOW_LOCAL_FALLBACK=True,
        )


def test_production_accepts_secure_configuration():
    # Production now also mandates Celery, an explicit MongoDB URI and an
    # explicit Redis URL (§12/§17): long-running AI processing may not run in
    # the API process and dev infrastructure defaults are rejected.
    s = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        JWT_SECRET_KEY="y" * 48,
        CORS_ORIGINS=["https://app.example.com"],
        ALLOW_LOCAL_FALLBACK=False,
        PROCESSING_QUEUE="celery",
        MONGODB_URI="mongodb://mongo.internal:27017",
        REDIS_URL="redis://redis.internal:6379/0",
    )
    assert s.JWT_SECRET_KEY == "y" * 48
    assert s.PROCESSING_QUEUE == "celery"
