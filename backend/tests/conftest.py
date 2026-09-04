import os
import sys
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
