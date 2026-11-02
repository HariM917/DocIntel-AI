import os
import sys
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is in sys.path
TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.database import db
from app.api.security import ensure_default_rules

TEST_PASSWORD = "SecurePassword123!"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initializes test environment and default rules."""
    import asyncio
    asyncio.run(db.connect())
    asyncio.run(ensure_default_rules())
    yield


@pytest.fixture
def client():
    """Yields FastAPI TestClient for HTTP requests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_manager():
    """Exposes the shared database manager for direct assertions in tests."""
    return db


def _register(client: TestClient, email: str, password: str = TEST_PASSWORD) -> str:
    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def unique_email():
    def _make(prefix: str = "user") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}@docintel.ai"
    return _make


@pytest.fixture
def auth_headers(client, unique_email):
    """Factory producing Authorization headers for a freshly registered user."""
    def _make(prefix: str = "user"):
        email = unique_email(prefix)
        token = _register(client, email)
        return {"Authorization": f"Bearer {token}"}, email
    return _make
