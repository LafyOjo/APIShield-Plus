import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"
os.environ.setdefault("DATABASE_URL", f"sqlite:///./cache_test_{uuid4().hex}.db")

from app.main import app
import app.core.access_log as access_log_module
import app.core.db as db_module
import app.core.policy as policy_module
from app.core.cache import (
    build_tenant_query_cache_key,
    build_cache_key,
    cache_clear,
    cache_get,
    db_scope_id,
    filters_hash,
    reset_cache_backend,
)
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.crud.website_environments import list_environments
from app.models.enums import RoleEnum
from app.models.trust_scoring import TrustSnapshot


client = TestClient(app)


@pytest.fixture(autouse=True)
def _enable_memory_cache():
    previous = os.environ.get("CACHE_BACKEND")
    os.environ["CACHE_BACKEND"] = "memory"
    reset_cache_backend()
    yield
    if previous is None:
        os.environ.pop("CACHE_BACKEND", None)
    else:
        os.environ["CACHE_BACKEND"] = previous
    reset_cache_backend()


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
    db_module.Base.metadata.drop_all(bind=engine)
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, trust_score: int):
    now = datetime.utcnow()
    with SessionLocal() as db:
        user = create_user(
            db,
            username=username,
            password_hash=get_password_hash("pw"),
            role="user",
        )
        tenant = create_tenant(db, name=tenant_name)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=RoleEnum.OWNER,
            created_by_user_id=user.id,
        )
        website = create_website(db, tenant.id, f"{tenant.slug}.example.com", created_by_user_id=user.id)
        env = list_environments(db, website.id)[0]
        snapshot = TrustSnapshot(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            bucket_start=now,
            path=None,
            trust_score=trust_score,
            confidence=0.8,
            factor_count=1,
            is_demo=False,
        )
        db.add(snapshot)
        db.commit()
        return tenant.slug, tenant.id


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_cache_key_includes_tenant_and_filters_hash():
    reset_cache_backend()
    cache_clear()
    key_a = build_cache_key(
        "map.summary",
        tenant_id=1,
        db_scope="db1",
        filters={"from": "2026-01-01T00:00:00Z"},
    )
    key_b = build_cache_key(
        "map.summary",
        tenant_id=2,
        db_scope="db1",
        filters={"from": "2026-01-01T00:00:00Z"},
    )
    key_c = build_cache_key(
        "map.summary",
        tenant_id=1,
        db_scope="db1",
        filters={"from": "2026-01-02T00:00:00Z"},
    )
    assert ":tenant:1:" in key_a
    assert key_a != key_b
    assert key_a != key_c


def test_tenant_query_cache_key_includes_required_dimensions():
    from_ts = datetime(2026, 1, 1, 0, 0, 0)
    to_ts = datetime(2026, 1, 2, 0, 0, 0)
    key = build_tenant_query_cache_key(
        "map.summary",
        tenant_id=42,
        website_id=7,
        env_id=3,
        from_ts=from_ts,
        to_ts=to_ts,
        filters={"category": "threat", "severity": "high"},
        db_scope="dbscope1",
    )
    assert ":tenant:42:" in key
    assert ":website:7:" in key
    assert ":env:3:" in key
    assert ":from:" in key
    assert ":to:" in key
    assert ":map.summary:" in key


def test_tenant_query_cache_key_changes_with_scope_or_filters():
    base_kwargs = {
        "prefix": "trust.snapshots",
        "tenant_id": 9,
        "website_id": 2,
        "env_id": 1,
        "from_ts": "2026-01-01T00:00:00Z",
        "to_ts": "2026-01-01T12:00:00Z",
    }
    key_a = build_tenant_query_cache_key(
        filters={"path": "/checkout"},
        db_scope="db-a",
        **base_kwargs,
    )
    key_b = build_tenant_query_cache_key(
        filters={"path": "/pricing"},
        db_scope="db-a",
        **base_kwargs,
    )
    key_c = build_tenant_query_cache_key(
        filters={"path": "/checkout"},
        db_scope="db-b",
        **base_kwargs,
    )
    key_d = build_tenant_query_cache_key(
        filters={"path": "/checkout"},
        db_scope="db-a",
        to_ts="2026-01-01T13:00:00Z",
        **{k: v for k, v in base_kwargs.items() if k != "to_ts"},
    )
    assert key_a != key_b
    assert key_a != key_c
    assert key_a != key_d


def test_tenant_query_cache_key_hash_matches_payload_dimensions():
    from_ts = datetime(2026, 3, 1, 12, 0, 0)
    to_ts = datetime(2026, 3, 1, 13, 0, 0)
    key = build_tenant_query_cache_key(
        "map.summary",
        tenant_id=55,
        website_id=8,
        env_id=4,
        from_ts=from_ts,
        to_ts=to_ts,
        filters={"category": "threat", "severity": "high"},
        db_scope="dbscope-x",
    )
    expected_hash = filters_hash(
        {
            "website_id": 8,
            "env_id": 4,
            "from": from_ts,
            "to": to_ts,
            "db": "dbscope-x",
            "category": "threat",
            "severity": "high",
        }
    )
    assert key.endswith(expected_hash)


def test_tenant_query_cache_key_uses_all_scope_placeholders_when_missing():
    key = build_tenant_query_cache_key(
        "revenue.leaks",
        tenant_id=12,
        website_id=None,
        env_id=None,
        from_ts=None,
        to_ts=None,
        filters={"limit": 20},
    )
    assert ":tenant:12:" in key
    assert ":website:all:" in key
    assert ":env:all:" in key
    assert ":from:none:" in key
    assert ":to:none:" in key


def test_cached_endpoint_returns_same_payload_and_hits_cache():
    reset_cache_backend()
    cache_clear()
    db_url = os.environ["DATABASE_URL"]
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id = _seed_tenant(
        SessionLocal,
        username="cache_user",
        tenant_name="Cache Tenant",
        trust_score=87,
    )
    token = _login("cache_user", tenant_slug)
    from_ts = datetime.utcnow() - timedelta(hours=1)
    to_ts = datetime.utcnow()

    resp = client.get(
        "/api/v1/trust/snapshots",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        params={"from": from_ts.isoformat(), "to": to_ts.isoformat()},
    )
    assert resp.status_code == 200
    first_payload = resp.json()
    assert first_payload

    with SessionLocal() as db:
        scope_id = db_scope_id(db)
        db.query(TrustSnapshot).delete()
        db.commit()

    cache_key = build_cache_key(
        "trust.snapshots",
        tenant_id=tenant_id,
        db_scope=scope_id,
        filters={
            "from": from_ts,
            "to": to_ts,
            "website_id": None,
            "env_id": None,
            "path": None,
            "limit": 500,
            "include_demo": False,
        },
    )
    cached = cache_get(cache_key, cache_name="trust.snapshots")
    assert cached is not None

    resp = client.get(
        "/api/v1/trust/snapshots",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
        params={"from": from_ts.isoformat(), "to": to_ts.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json() == first_payload


def test_cache_never_serves_cross_tenant_data():
    reset_cache_backend()
    cache_clear()
    db_url = os.environ["DATABASE_URL"]
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, _tenant_a_id = _seed_tenant(
        SessionLocal,
        username="tenant_a_user",
        tenant_name="Tenant A",
        trust_score=92,
    )
    tenant_b_slug, _tenant_b_id = _seed_tenant(
        SessionLocal,
        username="tenant_b_user",
        tenant_name="Tenant B",
        trust_score=61,
    )

    token_a = _login("tenant_a_user", tenant_a_slug)
    token_b = _login("tenant_b_user", tenant_b_slug)

    resp_a = client.get(
        "/api/v1/trust/snapshots",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp_a.status_code == 200
    resp_b = client.get(
        "/api/v1/trust/snapshots",
        headers={"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp_b.status_code == 200

    data_a = resp_a.json()
    data_b = resp_b.json()
    assert data_a
    assert data_b
    assert data_a[0]["trust_score"] != data_b[0]["trust_score"]
