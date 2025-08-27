import os
from datetime import datetime, timedelta

# Configure test database before importing app modules
os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.alerts import Alert  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

client = TestClient(app)


def _auth_headers():
    resp = client.post('/login', json={'username': 'admin', 'password': 'pw'})
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def current_chain():
    return client.get('/api/security/chain', headers=_auth_headers()).json()['chain']


def setup_function(_):
    with SessionLocal() as db:
        create_user(db, username='admin', password_hash=get_password_hash('pw'), role='admin')


def test_block_after_five_failures():
    chain = current_chain()
    for i in range(5):
        resp = client.post(
            '/score',
            json={'client_ip': '1.1.1.1', 'auth_result': 'failure', 'with_jwt': False},
            headers={'X-Chain-Password': chain},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['fails_last_minute'] == i + 1
        chain = current_chain()

    resp = client.post(
        '/score',
        json={'client_ip': '1.1.1.1', 'auth_result': 'failure', 'with_jwt': False},
        headers={'X-Chain-Password': chain},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'blocked'
    assert body['fails_last_minute'] == 6

    with SessionLocal() as db:
        assert db.query(Alert).count() == 6
        last = db.query(Alert).order_by(Alert.id.desc()).first()
        assert last.detail == 'Blocked: too many failures'


def test_old_failures_not_counted():
    old_time = datetime.utcnow() - timedelta(minutes=2)
    with SessionLocal() as db:
        for i in range(5):
            db.add(Alert(ip_address='2.2.2.2', total_fails=i+1, detail='old', timestamp=old_time))
        db.commit()

    chain = current_chain()
    resp = client.post(
        '/score',
        json={'client_ip': '2.2.2.2', 'auth_result': 'failure', 'with_jwt': False},
        headers={'X-Chain-Password': chain},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'ok'
    assert body['fails_last_minute'] == 1


def test_custom_fail_limit(monkeypatch):
    monkeypatch.setenv('FAIL_LIMIT', '3')
    chain = current_chain()
    for i in range(3):
        resp = client.post(
            '/score',
            json={'client_ip': '3.3.3.3', 'auth_result': 'failure', 'with_jwt': False},
            headers={'X-Chain-Password': chain},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        chain = current_chain()

    resp = client.post(
        '/score',
        json={'client_ip': '3.3.3.3', 'auth_result': 'failure', 'with_jwt': False},
        headers={'X-Chain-Password': chain},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'blocked'


def test_custom_window(monkeypatch):
    monkeypatch.setenv('FAIL_LIMIT', '1')
    monkeypatch.setenv('FAIL_WINDOW_SECONDS', '120')
    old_time = datetime.utcnow() - timedelta(seconds=90)
    with SessionLocal() as db:
        db.add(Alert(ip_address='4.4.4.4', total_fails=1, detail='old', timestamp=old_time))
        db.commit()

    chain = current_chain()
    resp = client.post(
        '/score',
        json={'client_ip': '4.4.4.4', 'auth_result': 'failure', 'with_jwt': False},
        headers={'X-Chain-Password': chain},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['status'] == 'blocked'


def test_invalid_chain_token_creates_alert():
    with SessionLocal() as db:
        start = db.query(Alert).count()
    resp = client.post(
        '/score',
        json={'client_ip': '6.6.6.6', 'auth_result': 'failure', 'with_jwt': False},
        headers={'X-Chain-Password': 'wrong'},
    )
    assert resp.status_code == 401
    with SessionLocal() as db:
        assert db.query(Alert).count() == start + 1
        last = db.query(Alert).order_by(Alert.id.desc()).first()
        assert last.detail == 'Blocked: invalid chain token'
