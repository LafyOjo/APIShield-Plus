import os
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ALLOW_RAW_IP_SECURITY_ENDPOINTS", "true")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.privacy import hash_ip
from app.core.security import get_password_hash
from app.crud.audit import create_audit_log
from app.crud.events import create_event
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.enums import RoleEnum
from app.models.events import Event
from app.models.plans import Plan


client = TestClient(app)


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    access_log_module.SessionLocal = SessionLocal
    policy_module.SessionLocal = SessionLocal
    access_log_module.create_access_log = lambda db, username, path: None
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, ip_value: str):
    with SessionLocal() as db:
        user = create_user(db, username=username, password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        create_event(
            db,
            tenant.id,
            username,
            "login",
            True,
            client_ip=ip_value,
            user_agent="test-agent/1.0",
            request_path="/login",
            referrer="https://example.com",
            country_code="US",
        )
        db.add(
            Alert(
                tenant_id=tenant.id,
                ip_address=ip_value,
                client_ip=ip_value,
                ip_hash=hash_ip(tenant.id, ip_value),
                user_agent="test-agent/1.0",
                request_path="/score",
                referrer="https://example.com",
                country_code="US",
                total_fails=1,
                detail="Failed login",
            )
        )
        create_audit_log(
            db,
            tenant_id=tenant.id,
            username=username,
            event="user_login_success",
            client_ip=ip_value,
            user_agent="test-agent/1.0",
            request_path="/audit",
            referrer="https://example.com",
            country_code="US",
        )
        db.commit()
        return tenant.slug, tenant.id, user.id


def _set_geo_data_aged(
    db,
    *,
    tenant_id: int,
    days_ago: int,
    country_code: str,
) -> None:
    cutoff = datetime.utcnow() - timedelta(days=days_ago)
    db.query(Event).filter(Event.tenant_id == tenant_id).update(
        {"timestamp": cutoff, "country_code": country_code},
        synchronize_session=False,
    )
    db.query(Alert).filter(Alert.tenant_id == tenant_id).update(
        {"timestamp": cutoff, "country_code": country_code},
        synchronize_session=False,
    )
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).update(
        {"timestamp": cutoff, "country_code": country_code},
        synchronize_session=False,
    )
    db.commit()


def _create_geo_records(
    db,
    *,
    tenant_id: int,
    username: str,
    ip_value: str,
    country_code: str,
) -> None:
    create_event(
        db,
        tenant_id,
        username,
        "login",
        True,
        client_ip=ip_value,
        user_agent="test-agent/2.0",
        request_path="/login",
        referrer="https://example.com",
        country_code=country_code,
    )
    db.add(
        Alert(
            tenant_id=tenant_id,
            ip_address=ip_value,
            client_ip=ip_value,
            ip_hash=hash_ip(tenant_id, ip_value),
            user_agent="test-agent/2.0",
            request_path="/score",
            referrer="https://example.com",
            country_code=country_code,
            total_fails=1,
            detail="Failed login",
        )
    )
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=username,
        event="user_login_success",
        client_ip=ip_value,
        user_agent="test-agent/2.0",
        request_path="/audit",
        referrer="https://example.com",
        country_code=country_code,
    )
    db.commit()


def test_security_ips_endpoint_tenant_scoped():
    db_url = f"sqlite:///./security_ips_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, tenant_a_id, _tenant_a_user_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        ip_value="203.0.113.10",
    )
    _tenant_b_slug, tenant_b_id, _tenant_b_user_id = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="Umbrella",
        ip_value="198.51.100.5",
    )

    token = _login("alice", tenant_a_slug)
    resp = client.get(
        "/api/v1/security/ips",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    ip_hashes = {item["ip_hash"] for item in payload["items"]}
    assert hash_ip(tenant_a_id, "203.0.113.10") in ip_hashes
    assert hash_ip(tenant_b_id, "198.51.100.5") not in ip_hashes


def test_security_ips_endpoint_does_not_return_raw_ip_by_default():
    db_url = f"sqlite:///./security_ips_raw_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, _tenant_id, _user_id = _seed_tenant(
        SessionLocal,
        username="carol",
        tenant_name="Wayne",
        ip_value="192.0.2.9",
    )

    token = _login("carol", tenant_slug)
    resp = client.get(
        "/api/v1/security/ips",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    assert payload["items"][0]["client_ip"] is None


def test_security_locations_endpoint_returns_counts():
    db_url = f"sqlite:///./security_locations_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, _tenant_id, _user_id = _seed_tenant(
        SessionLocal,
        username="diana",
        tenant_name="Themyscira",
        ip_value="203.0.113.77",
    )

    token = _login("diana", tenant_slug)
    resp = client.get(
        "/api/v1/security/locations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    assert payload["items"][0]["country_code"] == "US"
    assert payload["items"][0]["count"] >= 1


def test_geo_map_feature_flag_blocks_or_limits_security_location_data():
    db_url = f"sqlite:///./security_geo_limit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id = _seed_tenant(
        SessionLocal,
        username="edward",
        tenant_name="Gotham",
        ip_value="203.0.113.90",
    )
    with SessionLocal() as db:
        _set_geo_data_aged(db, tenant_id=tenant_id, days_ago=3, country_code="FR")
        _create_geo_records(
            db,
            tenant_id=tenant_id,
            username="edward",
            ip_value="203.0.113.91",
            country_code="US",
        )

    token = _login("edward", tenant_slug)
    resp = client.get(
        "/api/v1/security/locations",
        params={"from": (datetime.utcnow() - timedelta(days=30)).isoformat()},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    codes = {item["country_code"] for item in payload["items"]}
    assert "US" in codes
    assert "FR" not in codes


def test_geo_history_days_clamps_time_range():
    db_url = f"sqlite:///./security_geo_history_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id = _seed_tenant(
        SessionLocal,
        username="frank",
        tenant_name="Central",
        ip_value="198.51.100.20",
    )
    with SessionLocal() as db:
        plan = Plan(
            name="GeoPro",
            price_monthly=99,
            limits_json={"geo_history_days": 2, "raw_ip_retention_days": 7},
            features_json={"geo_map": True},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)
        _set_geo_data_aged(db, tenant_id=tenant_id, days_ago=10, country_code="DE")
        _create_geo_records(
            db,
            tenant_id=tenant_id,
            username="frank",
            ip_value="198.51.100.21",
            country_code="US",
        )

    token = _login("frank", tenant_slug)
    resp = client.get(
        "/api/v1/security/locations",
        params={"from": (datetime.utcnow() - timedelta(days=30)).isoformat()},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    codes = {item["country_code"] for item in payload["items"]}
    assert "US" in codes
    assert "DE" not in codes


def test_raw_ip_access_requires_owner_and_within_retention_window_if_enabled():
    db_url = f"sqlite:///./security_raw_ip_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, owner_id = _seed_tenant(
        SessionLocal,
        username="gina",
        tenant_name="Star",
        ip_value="192.0.2.55",
    )
    with SessionLocal() as db:
        viewer = create_user(
            db,
            username="hank",
            password_hash=get_password_hash("pw"),
            role="user",
        )
        create_membership(
            db,
            tenant_id=tenant_id,
            user_id=viewer.id,
            role=RoleEnum.VIEWER,
            created_by_user_id=owner_id,
        )
        plan = Plan(
            name="GeoEnabled",
            price_monthly=149,
            limits_json={"geo_history_days": 7, "raw_ip_retention_days": 1},
            features_json={"geo_map": True},
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        set_tenant_plan(db, tenant_id, plan.id)

    owner_token = _login("gina", tenant_slug)
    resp = client.get(
        "/api/v1/security/ips",
        params={"include_raw_ip": "true"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    assert payload["items"][0]["client_ip"] == "192.0.2.55"

    viewer_token = _login("hank", tenant_slug)
    resp = client.get(
        "/api/v1/security/ips",
        params={"include_raw_ip": "true"},
        headers={"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"][0]["client_ip"] is None

    with SessionLocal() as db:
        _set_geo_data_aged(db, tenant_id=tenant_id, days_ago=3, country_code="US")

    resp = client.get(
        "/api/v1/security/ips",
        params={"include_raw_ip": "true"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"][0]["client_ip"] is None
