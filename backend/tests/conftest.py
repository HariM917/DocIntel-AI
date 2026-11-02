import os
import sys
import time
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# The suite exercises application logic against the deterministic local fallback
# store, and test bodies call `asyncio.run(...)` on the shared db manager many
# times. That is only safe while no live Motor client is bound to a specific
# event loop, so pin MongoDB to an unreachable endpoint: the local fallback is
# then selected regardless of whether a developer happens to have MongoDB
# running (e.g. via docker compose). Must be set before `app.config` is imported.
os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:1"
os.environ["ALLOW_LOCAL_FALLBACK"] = "true"

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

    async def _initialize() -> None:
        await db.connect()
        await ensure_default_rules()

    # Both calls share a single event loop. Running them via two separate
    # `asyncio.run(...)` calls closed the first loop while the shared db manager
    # still referenced it, which surfaced as "Event loop is closed" (or a
    # different-loop error) as soon as a real MongoDB was reachable.
    asyncio.run(_initialize())
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
