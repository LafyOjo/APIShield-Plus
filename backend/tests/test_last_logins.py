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
        create_user(db, username='ben', password_hash=get_password_hash('pw2'))


def test_last_login_endpoint():
    client.post('/login', json={'username': 'alice', 'password': 'pw'})
    client.post('/login', json={'username': 'ben', 'password': 'pw2'})

    token = create_access_token({"sub": "alice"})
    resp = client.get('/api/last-logins', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.json()
    assert 'alice' in data and 'ben' in data
    assert isinstance(data['alice'], str)
