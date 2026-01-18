import os
from uuid import uuid4
import time

os.environ['DATABASE_URL'] = f"sqlite:///./test_{uuid4().hex}.db"
os.environ['SECRET_KEY'] = 'test-secret'
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user, get_user_by_username  # noqa: E402
from app.models.tenants import Tenant  # noqa: E402

client = TestClient(app)
TENANT_HEADER = "X-Tenant-ID"
TENANT_SLUG = "default"


def setup_function(_):
    with SessionLocal() as db:
        user = get_user_by_username(db, "alice")
        if user is None:
            user = create_user(db, username='alice', password_hash=get_password_hash('pw'))
        tenant = db.query(Tenant).filter(Tenant.slug == TENANT_SLUG).first()
        if tenant is None:
            tenant = create_tenant(db, name="Default Workspace", slug=TENANT_SLUG)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role="owner",
            created_by_user_id=user.id,
        )


def test_login_event_logged():
    resp = client.post(
        '/login',
        json={'username': 'alice', 'password': 'pw'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )
    assert resp.status_code == 200
    token = resp.json()['access_token']
    resp = client.get(
        '/api/events',
        headers={
            'Authorization': f'Bearer {token}',
            TENANT_HEADER: TENANT_SLUG,
        },
    )
    assert resp.status_code == 200
    events = resp.json()
    assert any(e['action'] == 'login' and e['success'] for e in events)


def test_logout_event_logged():
    resp = client.post(
        '/login',
        json={'username': 'alice', 'password': 'pw'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )
    assert resp.status_code == 200
    token = resp.json()['access_token']

    resp = client.post(
        '/logout',
        headers={'Authorization': f'Bearer {token}', TENANT_HEADER: TENANT_SLUG},
    )
    assert resp.status_code == 200

    time.sleep(1)
    resp = client.post(
        '/login',
        json={'username': 'alice', 'password': 'pw'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )
    assert resp.status_code == 200
    new_token = resp.json()['access_token']

    resp = client.get(
        '/api/events',
        headers={
            'Authorization': f'Bearer {new_token}',
            TENANT_HEADER: TENANT_SLUG,
        },
    )
    headers = {'Authorization': f'Bearer {token}', TENANT_HEADER: TENANT_SLUG}

    resp = client.post('/logout', headers=headers)
    assert resp.status_code == 401

    # Obtain a new token to access the events endpoint
    resp = client.post(
        '/login',
        json={'username': 'alice', 'password': 'pw'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )
    token = resp.json()['access_token']
    resp = client.get(
        '/api/events',
        headers={
            'Authorization': f'Bearer {token}',
            TENANT_HEADER: TENANT_SLUG,
        },
    )

    assert resp.status_code == 200
    events = resp.json()
    assert any(e['action'] == 'logout' and e['success'] for e in events)
