import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from datetime import timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
import app.api.auth as auth_module  # noqa: E402

client = TestClient(app)


def test_register_and_login():
    resp = client.post('/register', json={'username': 'alice', 'password': 'secret'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['username'] == 'alice'

    resp = client.post('/login', json={'username': 'alice', 'password': 'secret'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    assert token


def test_login_uses_expire_setting(monkeypatch):
    monkeypatch.setattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 5)

    captured = {}

    def fake_create(data, expires_delta):
        captured['delta'] = expires_delta
        return 'tok'

    monkeypatch.setattr(auth_module, 'create_access_token', fake_create)

    client.post('/register', json={'username': 'bob', 'password': 'pw'})
    resp = client.post('/login', json={'username': 'bob', 'password': 'pw'})
    assert resp.status_code == 200
    assert resp.json()['access_token'] == 'tok'
    assert captured['delta'] == timedelta(minutes=5)


def test_register_forward(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout=3):
        captured['url'] = url
        captured['payload'] = json

        class R:
            status_code = 200
        return R()

    monkeypatch.setattr(auth_module.requests, 'post', fake_post)
    monkeypatch.setenv('REGISTER_WITH_DEMOSHOP', 'true')
    monkeypatch.setenv('DEMO_SHOP_URL', 'http://shop')

    resp = client.post('/register', json={'username': 'carol', 'password': 'pw'})
    assert resp.status_code == 200
    assert captured['url'] == 'http://shop/register'
    assert captured['payload'] == {'username': 'carol', 'password': 'pw'}


def test_login_forward(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout=3):
        captured['url'] = url
        captured['payload'] = json

        class R:
            status_code = 200
        return R()

    monkeypatch.setattr(auth_module.requests, 'post', fake_post)
    monkeypatch.setenv('LOGIN_WITH_DEMOSHOP', 'true')
    monkeypatch.setenv('DEMO_SHOP_URL', 'http://shop')

    client.post('/register', json={'username': 'dan', 'password': 'pw'})
    resp = client.post('/login', json={'username': 'dan', 'password': 'pw'})
    assert resp.status_code == 200
    assert captured['url'] == 'http://shop/login'
    assert captured['payload'] == {'username': 'dan', 'password': 'pw'}


def test_login_forward_error_logged(monkeypatch):
    def fake_post(url, json, timeout=3):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_module.requests, 'post', fake_post)
    monkeypatch.setenv('LOGIN_WITH_DEMOSHOP', 'true')
    monkeypatch.setenv('DEMO_SHOP_URL', 'http://shop')

    client.post('/register', json={'username': 'eve', 'password': 'pw'})
    resp = client.post('/login', json={'username': 'eve', 'password': 'pw'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    resp = client.get('/api/events', headers={'Authorization': f'Bearer {token}'})
    assert any(e['action'] == 'shop_login_error' for e in resp.json())


def test_logout_revokes_token():
    client.post('/register', json={'username': 'erin', 'password': 'pw'})
    resp = client.post('/login', json={'username': 'erin', 'password': 'pw'})
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    resp = client.post('/logout', headers=headers)
    assert resp.status_code == 200

    resp = client.get('/api/me', headers=headers)
    assert resp.status_code == 401
