import os

# Setup env before imports
os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

client = TestClient(app)


def setup_function(_):
    # reset flag for each test
    from app.api import security
    security.SECURITY_ENABLED = True
    with SessionLocal() as db:
        create_user(db, username="admin", password_hash=get_password_hash("pw"), role="admin")


def _auth_headers():
    resp = client.post('/login', json={'username': 'admin', 'password': 'pw'})
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}




def test_get_security_default():
    resp = client.get('/api/security', headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()['enabled'] is True


def test_toggle_security():
    resp = client.post('/api/security', json={'enabled': False}, headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()['enabled'] is False
    resp = client.get('/api/security', headers=_auth_headers())
    assert resp.json()['enabled'] is False


def test_score_not_blocked_when_disabled():
    # disable security
    client.post('/api/security', json={'enabled': False}, headers=_auth_headers())
    # Send failures exceeding threshold
    for i in range(6):
        resp = client.post('/score', json={'client_ip': '9.9.9.9', 'auth_result': 'failure'})
        assert resp.status_code == 200
        # should never be blocked
        assert resp.json()['status'] == 'ok'
