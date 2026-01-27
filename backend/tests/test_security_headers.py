import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app


client = TestClient(app)


def test_security_headers_present_on_responses():
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") in {"DENY", "SAMEORIGIN"}
    assert resp.headers.get("Referrer-Policy")
    assert resp.headers.get("Content-Security-Policy")
