import os
import threading
from uuid import uuid4

os.environ["DATABASE_URL"] = f"sqlite:///./test_audit_{uuid4().hex}.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user, get_user_by_username  # noqa: E402
from app.models.audit_logs import AuditLog  # noqa: E402
from app.models.tenants import Tenant  # noqa: E402

client = TestClient(app)
TENANT_HEADER = "X-Tenant-ID"


def _ensure_tenant_and_user(tenant_slug: str, username: str, role: str = "owner"):
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            tenant = create_tenant(db, name=f"{tenant_slug} workspace", slug=tenant_slug)
        user = get_user_by_username(db, username)
        if user is None:
            user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            created_by_user_id=user.id,
        )
        token = create_access_token({"sub": user.username})
        return tenant.id, tenant.slug, token


def test_audit_log_write_includes_tenant_id():
    tenant_id, tenant_slug, token = _ensure_tenant_and_user("t1", "alice")
    resp = client.post(
        "/api/audit/log",
        json={"event": "user_login_success", "username": "alice"},
        headers={"Authorization": f"Bearer {token}", TENANT_HEADER: tenant_slug},
    )
    assert resp.status_code == 200
    with SessionLocal() as db:
        row = db.query(AuditLog).filter(AuditLog.event == "user_login_success").first()
        assert row is not None
        assert row.tenant_id == tenant_id


def test_audit_list_is_tenant_scoped():
    tenant_a_id, tenant_a_slug, token_a = _ensure_tenant_and_user("t1", "alice")
    _tenant_b_id, tenant_b_slug, token_b = _ensure_tenant_and_user("t2", "bob")

    client.post(
        "/api/audit/log",
        json={"event": "user_login_success", "username": "alice"},
        headers={"Authorization": f"Bearer {token_a}", TENANT_HEADER: tenant_a_slug},
    )
    client.post(
        "/api/audit/log",
        json={"event": "user_logout", "username": "bob"},
        headers={"Authorization": f"Bearer {token_b}", TENANT_HEADER: tenant_b_slug},
    )

    resp = client.get(
        "/api/audit",
        headers={"Authorization": f"Bearer {token_a}", TENANT_HEADER: tenant_a_slug},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert rows
    assert all(row["tenant_id"] == tenant_a_id for row in rows)


def test_audit_ws_scoped_broadcast_only_to_same_tenant():
    _tenant_a_id, tenant_a_slug, token_a = _ensure_tenant_and_user("t1", "alice")
    _tenant_b_id, tenant_b_slug, token_b = _ensure_tenant_and_user("t2", "bob")

    with client.websocket_connect(
        "/api/audit/ws",
        headers={"Authorization": f"Bearer {token_a}", TENANT_HEADER: tenant_a_slug},
    ) as ws_a, client.websocket_connect(
        "/api/audit/ws",
        headers={"Authorization": f"Bearer {token_b}", TENANT_HEADER: tenant_b_slug},
    ) as ws_b:
        client.post(
            "/api/audit/log",
            json={"event": "user_login_success", "username": "alice"},
            headers={"Authorization": f"Bearer {token_a}", TENANT_HEADER: tenant_a_slug},
        )
        client.post(
            "/api/audit/log",
            json={"event": "user_logout", "username": "bob"},
            headers={"Authorization": f"Bearer {token_b}", TENANT_HEADER: tenant_b_slug},
        )

        msg_a = ws_a.receive_json()
        assert msg_a["event"] == "user_login_success"

        msg_b = ws_b.receive_json()
        assert msg_b["event"] == "user_logout"

        received_a = {}

        def _receive_a():
            try:
                received_a["payload"] = ws_a.receive_json()
            except Exception as exc:
                received_a["error"] = exc

        thread_a = threading.Thread(target=_receive_a, daemon=True)
        thread_a.start()
        thread_a.join(timeout=0.2)
        assert thread_a.is_alive()
        ws_a.close()
        thread_a.join(timeout=1)


def test_audit_log_rejects_invalid_event():
    _tenant_id, tenant_slug, token = _ensure_tenant_and_user("t1", "alice")
    resp = client.post(
        "/api/audit/log",
        json={"event": "invalid_event", "username": "alice"},
        headers={"Authorization": f"Bearer {token}", TENANT_HEADER: tenant_slug},
    )
    assert resp.status_code == 422
