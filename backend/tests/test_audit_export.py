import os
from datetime import datetime, timedelta
from uuid import uuid4

os.environ["DATABASE_URL"] = f"sqlite:///./audit_export_{uuid4().hex}.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ALLOW_RAW_IP_SECURITY_ENDPOINTS"] = "true"
os.environ["SKIP_MIGRATIONS"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.core.entitlements import invalidate_entitlement_cache  # noqa: E402
from app.crud.audit import create_audit_log  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user, get_user_by_username  # noqa: E402
from app.models.feature_entitlements import FeatureEntitlement  # noqa: E402
from app.models.tenants import Tenant  # noqa: E402


client = TestClient(app)
TENANT_HEADER = "X-Tenant-ID"

Base.metadata.create_all(bind=engine)


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
        return tenant.id, tenant.slug, token, user.username


def _seed_audit_log(tenant_id: int, username: str, *, client_ip: str | None = None, ip_hash: str | None = None):
    with SessionLocal() as db:
        log = create_audit_log(
            db,
            tenant_id=tenant_id,
            username=username,
            event="audit.test",
            request=None,
            client_ip=client_ip,
            ip_hash=ip_hash,
        )
        return log


def test_audit_export_tenant_scoped():
    tenant_a_id, tenant_a_slug, token_a, user_a = _ensure_tenant_and_user("audit-a", "alice")
    tenant_b_id, _tenant_b_slug, _token_b, user_b = _ensure_tenant_and_user("audit-b", "bob")

    _seed_audit_log(tenant_a_id, user_a)
    _seed_audit_log(tenant_b_id, user_b)

    resp = client.get(
        "/api/v1/audit/export?format=json",
        headers={"Authorization": f"Bearer {token_a}", TENANT_HEADER: tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    records = payload.get("records") or []
    assert records
    assert all(row["tenant_id"] == tenant_a_id for row in records)


def test_audit_export_redacts_sensitive_fields():
    tenant_id, tenant_slug, token, username = _ensure_tenant_and_user("audit-redact", "carol")
    log = _seed_audit_log(tenant_id, username, client_ip="203.0.113.10", ip_hash="hash-123")

    with SessionLocal() as db:
        log_row = db.query(type(log)).filter(type(log).id == log.id).first()
        log_row.timestamp = datetime.utcnow() - timedelta(days=30)
        db.commit()

    resp = client.get(
        "/api/v1/audit/export?format=json",
        headers={"Authorization": f"Bearer {token}", TENANT_HEADER: tenant_slug},
    )
    assert resp.status_code == 200
    records = resp.json()["records"]
    record = next(item for item in records if item["event"] == "audit.test")
    assert record["client_ip"] is None
    assert record["ip_hash"] is None

    with SessionLocal() as db:
        db.add(
            FeatureEntitlement(
                tenant_id=tenant_id,
                feature="audit_export_ip_hash",
                enabled=True,
                source="manual_override",
            )
        )
        db.commit()

    invalidate_entitlement_cache(tenant_id)

    resp = client.get(
        "/api/v1/audit/export?format=json",
        headers={"Authorization": f"Bearer {token}", TENANT_HEADER: tenant_slug},
    )
    assert resp.status_code == 200
    records = resp.json()["records"]
    record = next(item for item in records if item["event"] == "audit.test")
    assert record["client_ip"] is None
    assert record["ip_hash"] == "hash-123"


def test_audit_export_streaming_does_not_memory_blowup():
    tenant_id, tenant_slug, token, username = _ensure_tenant_and_user("audit-stream", "drew")
    _seed_audit_log(tenant_id, username)

    with client.stream(
        "GET",
        "/api/v1/audit/export?format=csv",
        headers={"Authorization": f"Bearer {token}", TENANT_HEADER: tenant_slug},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("X-Export-Streaming") == "1"
        lines = []
        for line in resp.iter_lines():
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            lines.append(line)
            if len(lines) >= 3:
                break
        assert any("tenant_id" in line for line in lines)
