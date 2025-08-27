import os
import time

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


def test_login_event_logged():
    resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    resp = client.get('/api/events', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    events = resp.json()
    assert any(e['action'] == 'login' and e['success'] for e in events)


def test_logout_event_logged():
    resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
    assert resp.status_code == 200
    token = resp.json()['access_token']

    resp = client.post('/logout', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200

    time.sleep(1)
    resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
    assert resp.status_code == 200
    new_token = resp.json()['access_token']

    resp = client.get('/api/events', headers={'Authorization': f'Bearer {new_token}'})
    headers = {'Authorization': f'Bearer {token}'}

    resp = client.post('/logout', headers=headers)
    assert resp.status_code == 401

    # Obtain a new token to access the events endpoint
    resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
    token = resp.json()['access_token']
    resp = client.get('/api/events', headers={'Authorization': f'Bearer {token}'})

    assert resp.status_code == 200
    events = resp.json()
    assert any(e['action'] == 'logout' and e['success'] for e in events)
