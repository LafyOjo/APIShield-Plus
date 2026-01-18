import os

from fastapi.testclient import TestClient

os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.main import app  # noqa: E402


def test_health_endpoint_versioned():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["message"] == "pong"


def test_legacy_ping_still_available():
    client = TestClient(app)
    resp = client.get("/ping")
    assert resp.status_code == 200
