import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.audit_logs import AuditLog  # noqa: E402

client = TestClient(app)


def test_audit_log_persists_event():
    resp = client.post('/api/audit/log', json={'event': 'user_login_success', 'username': 'alice'})
    assert resp.status_code == 200
    with SessionLocal() as db:
        rows = db.query(AuditLog).all()
        assert any(r.event == 'user_login_success' and r.username == 'alice' for r in rows)


def test_audit_log_rejects_invalid_event():
    resp = client.post('/api/audit/log', json={'event': 'invalid_event', 'username': 'alice'})
    assert resp.status_code == 422
