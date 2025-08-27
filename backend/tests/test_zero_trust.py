import os

import importlib  # noqa: E402
import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
import app.core.zero_trust as zero_trust  # noqa: E402
import app.main as main_module  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

# Client will be initialised in setup_function after reloading the app
client = None


def setup_function(_):
    os.environ['ZERO_TRUST_API_KEY'] = 'secret-key'
    importlib.reload(zero_trust)
    importlib.reload(main_module)
    global client
    client = TestClient(main_module.app)
    with SessionLocal() as db:
        create_user(db, username='admin', password_hash=get_password_hash('pw'), role='admin')


def _auth_headers():
    resp = client.post('/login', json={'username': 'admin', 'password': 'pw'})
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def teardown_function(_):
    os.environ.pop('ZERO_TRUST_API_KEY', None)
    importlib.reload(zero_trust)
    importlib.reload(main_module)


def test_requires_api_key():
    resp = client.get('/config', headers=_auth_headers())
    assert resp.status_code == 401


def test_valid_api_key():
    headers = _auth_headers()
    headers['X-API-Key'] = 'secret-key'
    resp = client.get('/config', headers=headers)
    assert resp.status_code == 200


def test_invalid_key_records_score():
    resp = client.get('/config', headers=_auth_headers())
    assert resp.status_code == 401
    with SessionLocal() as db:
        from app.models.alerts import Alert
        assert db.query(Alert).count() == 1
