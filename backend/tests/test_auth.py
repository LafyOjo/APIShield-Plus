import os
from uuid import uuid4

os.environ['DATABASE_URL'] = f"sqlite:///./test_{uuid4().hex}.db"
os.environ['SECRET_KEY'] = 'test-secret'
os.environ["SKIP_MIGRATIONS"] = "1"

from datetime import timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_access_token, decode_access_token  # noqa: E402
import app.api.auth as auth_module  # noqa: E402
from app.crud.plans import get_plan_by_name  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.models.tenants import Tenant  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.memberships import Membership  # noqa: E402
from app.models.tenant_settings import TenantSettings  # noqa: E402
from app.models.data_retention import DataRetentionPolicy  # noqa: E402
from app.models.subscriptions import Subscription  # noqa: E402
from app.models.enums import RoleEnum  # noqa: E402
from app.crud.users import get_user_by_username  # noqa: E402

client = TestClient(app)
TENANT_HEADER = "X-Tenant-ID"


def _ensure_free_plan() -> None:
    with SessionLocal() as db:
        if get_plan_by_name(db, "Free") is None:
            plan = Plan(
                name="Free",
                price_monthly=0,
                limits_json={"websites": 1},
                features_json={"heatmaps": False},
                is_active=True,
            )
            db.add(plan)
            db.commit()


def test_register_and_login():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'alice', 'password': 'secret'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['username'] == 'alice'
    assert data['active_tenant_id']
    assert data['active_tenant_slug']

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

    _ensure_free_plan()
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

    _ensure_free_plan()
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

    _ensure_free_plan()
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

    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'eve', 'password': 'pw'})
    tenant_slug = resp.json()['active_tenant_slug']
    resp = client.post(
        '/login',
        json={'username': 'eve', 'password': 'pw'},
        headers={TENANT_HEADER: tenant_slug},
    )
    assert resp.status_code == 200
    token = resp.json()['access_token']
    resp = client.get(
        '/api/events',
        headers={'Authorization': f'Bearer {token}', TENANT_HEADER: tenant_slug},
    )
    assert any(e['action'] == 'shop_login_error' for e in resp.json())


def test_logout_revokes_token():
    _ensure_free_plan()
    client.post('/register', json={'username': 'erin', 'password': 'pw'})
    resp = client.post('/login', json={'username': 'erin', 'password': 'pw'})
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    resp = client.post('/logout', headers=headers)
    assert resp.status_code == 200

    resp = client.get('/api/me', headers=headers)
    assert resp.status_code == 401


def test_register_creates_tenant_and_owner_membership():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'frank', 'password': 'pw'})
    assert resp.status_code == 200
    data = resp.json()
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == data['active_tenant_id']).first()
        assert tenant is not None
        user = get_user_by_username(db, 'frank')
        assert user is not None
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
            .first()
        )
        assert membership is not None
        assert membership.role == RoleEnum.OWNER


def test_register_rolls_back_if_tenant_creation_fails(monkeypatch):
    _ensure_free_plan()

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_module, 'create_tenant_with_owner', boom)
    resp = client.post('/register', json={'username': 'grace', 'password': 'pw'})
    assert resp.status_code == 500
    with SessionLocal() as db:
        assert get_user_by_username(db, 'grace') is None


def test_register_assigns_free_plan_subscription_stub():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'hank', 'password': 'pw'})
    assert resp.status_code == 200
    data = resp.json()
    with SessionLocal() as db:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.tenant_id == data['active_tenant_id'])
            .first()
        )
        assert subscription is not None
        plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        assert plan is not None
        assert plan.name == 'Free'


def test_register_creates_default_settings_and_retention():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'ivy', 'password': 'pw'})
    assert resp.status_code == 200
    data = resp.json()
    with SessionLocal() as db:
        settings_row = (
            db.query(TenantSettings)
            .filter(TenantSettings.tenant_id == data['active_tenant_id'])
            .first()
        )
        assert settings_row is not None
        policies = (
            db.query(DataRetentionPolicy)
            .filter(DataRetentionPolicy.tenant_id == data['active_tenant_id'])
            .all()
        )
        assert policies


def test_jwt_contains_membership_snapshot_if_enabled():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'jack', 'password': 'pw'})
    assert resp.status_code == 200
    tenant_id = resp.json()['active_tenant_id']
    resp = client.post('/login', json={'username': 'jack', 'password': 'pw'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    payload = decode_access_token(token)
    memberships = payload.get('memberships')
    assert isinstance(memberships, list)
    assert {'tenant_id': tenant_id, 'role': 'owner'} in memberships


def test_authorization_does_not_trust_jwt_membership_snapshot():
    _ensure_free_plan()
    resp = client.post('/register', json={'username': 'kate', 'password': 'pw'})
    assert resp.status_code == 200
    with SessionLocal() as db:
        user = get_user_by_username(db, 'kate')
        assert user is not None
        other_tenant = create_tenant(db, name='Other Tenant', slug='other-tenant')
        other_tenant_id = other_tenant.id
        other_slug = other_tenant.slug
    token = create_access_token(
        data={
            'sub': 'kate',
            'memberships': [{'tenant_id': other_tenant_id, 'role': 'owner'}],
        }
    )
    resp = client.get(
        '/config',
        headers={'Authorization': f'Bearer {token}', TENANT_HEADER: other_slug},
    )
    expected = 404 if settings.TENANT_STRICT_404 else 403
    assert resp.status_code == expected
