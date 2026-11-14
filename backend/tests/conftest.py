import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}"  # set TEST_DATABASE_URL to run against PostgreSQL
os.environ["LLM_ENABLED"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SEED_ON_STARTUP"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs lifespan -> create tables + seed
        yield c


@pytest.fixture(scope="session")
def customers(client):
    return {c["full_name"]: c for c in client.get("/api/customers").json()}
