import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.crud.users import create_user  # noqa: E402

client = TestClient(app)


def setup_function(_):
    with SessionLocal() as db:
        create_user(db, username='alice', password_hash=get_password_hash('pw'))


def test_access_logs_recorded():
    token = create_access_token({'sub': 'alice'})
    headers = {'Authorization': f'Bearer {token}'}

    client.get('/ping', headers=headers)

    resp = client.get('/api/access-logs', headers=headers)
    assert resp.status_code == 200
    logs = resp.json()
    assert any(log['path'] == '/ping' for log in logs)
    assert all(log['username'] == 'alice' for log in logs)
