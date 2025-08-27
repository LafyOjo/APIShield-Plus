import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402

client = TestClient(app)


def setup_function(_):
    with SessionLocal() as db:
        create_user(db, username='alice', password_hash=get_password_hash('pw'))


def _auth_headers():
    resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_me_returns_password_hash_and_username():
    resp = client.get('/api/me', headers=_auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data['username'] == 'alice'
    assert 'password_hash' in data and data['password_hash']
