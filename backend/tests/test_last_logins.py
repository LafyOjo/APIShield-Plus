import os
from uuid import uuid4
os.environ['DATABASE_URL'] = f"sqlite:///./test_{uuid4().hex}.db"
os.environ['SECRET_KEY'] = 'test-secret'
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.models.tenants import Tenant  # noqa: E402

client = TestClient(app)
TENANT_HEADER = "X-Tenant-ID"
TENANT_SLUG = "default"


def setup_function(_):
    with SessionLocal() as db:
        alice = create_user(db, username='alice', password_hash=get_password_hash('pw'))
        ben = create_user(db, username='ben', password_hash=get_password_hash('pw2'))
        tenant = db.query(Tenant).filter(Tenant.slug == TENANT_SLUG).first()
        if tenant is None:
            tenant = create_tenant(db, name="Default Workspace", slug=TENANT_SLUG)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=alice.id,
            role="owner",
            created_by_user_id=alice.id,
        )
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=ben.id,
            role="viewer",
            created_by_user_id=alice.id,
        )


def test_last_login_endpoint():
    client.post(
        '/login',
        json={'username': 'alice', 'password': 'pw'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )
    client.post(
        '/login',
        json={'username': 'ben', 'password': 'pw2'},
        headers={TENANT_HEADER: TENANT_SLUG},
    )

    token = create_access_token({"sub": "alice"})
    resp = client.get(
        '/api/last-logins',
        headers={'Authorization': f'Bearer {token}', TENANT_HEADER: TENANT_SLUG},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'alice' in data and 'ben' in data
    assert isinstance(data['alice'], str)
