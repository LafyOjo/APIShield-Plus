import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.core.usage import (
    get_or_create_current_period_usage,
    increment_events,
    increment_storage,
)
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.models.tenant_usage import TenantUsage


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


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_usage_record_created_for_month():
    db_url = f"sqlite:///./usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        now = datetime(2025, 5, 10, tzinfo=timezone.utc)
        usage = get_or_create_current_period_usage(tenant.id, db=db, now=now)
        assert usage.tenant_id == tenant.id
        assert usage.period_start.year == 2025
        assert usage.period_start.month == 5
        assert usage.period_start.day == 1
        assert usage.events_ingested == 0
        assert usage.storage_bytes == 0


def test_increment_updates_counters():
    db_url = f"sqlite:///./usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Umbrella")
        increment_events(tenant.id, 3, db=db)
        increment_storage(tenant.id, 2048, db=db)
        usage = (
            db.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant.id)
            .first()
        )
        assert usage is not None
        assert usage.events_ingested == 3
        assert usage.storage_bytes == 2048


def test_usage_unique_constraint_enforced():
    db_url = f"sqlite:///./usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Wayne")
        now = datetime(2026, 1, 5, tzinfo=timezone.utc)
        usage = get_or_create_current_period_usage(tenant.id, db=db, now=now)
        duplicate = TenantUsage(
            tenant_id=tenant.id,
            period_start=usage.period_start,
            period_end=usage.period_end,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_cross_tenant_usage_blocked():
    db_url = f"sqlite:///./usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="alice", password_hash=get_password_hash("pw"), role="user")
        tenant_a = create_tenant(db, name="TenantA")
        tenant_b = create_tenant(db, name="TenantB")
        create_membership(
            db,
            tenant_id=tenant_a.id,
            user_id=user.id,
            role="owner",
            created_by_user_id=user.id,
        )
        tenant_b_slug = tenant_b.slug

    token = _login("alice")
    resp = client.get(
        "/api/v1/usage",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_b_slug},
    )
    assert resp.status_code in {403, 404}
