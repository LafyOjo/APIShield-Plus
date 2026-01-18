import os
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.models  # noqa: F401
from app.core.db import Base
from app.models.enums import RoleEnum
from app.models.memberships import Membership
from app.models.tenants import Tenant
from app.models.users import User


def load_backfill_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "upgrade_to_multitenant.py"
    spec = importlib.util.spec_from_file_location("upgrade_to_multitenant", module_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Could not load upgrade_to_multitenant module")
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db_setup(tmp_path):
    db_url = f"sqlite:///{tmp_path}/backfill_test.db"
    os.environ["DATABASE_URL"] = db_url
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, TestingSessionLocal


def test_backfill_creates_default_tenant_and_memberships(db_setup):
    engine, SessionLocal = db_setup
    upgrade = load_backfill_module()

    with SessionLocal() as db:
        admin_user = User(username="admin", password_hash="x", role="admin")
        viewer_user = User(username="viewer", password_hash="x", role="user")
        db.add_all([admin_user, viewer_user])
        db.commit()
        db.refresh(admin_user)
        db.refresh(viewer_user)
        admin_id = admin_user.id
        viewer_id = viewer_user.id

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE events"))
        conn.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, "
                "tenant_id INTEGER NULL, "
                "username VARCHAR, "
                "action VARCHAR NOT NULL, "
                "success BOOLEAN NOT NULL, "
                "timestamp DATETIME NOT NULL"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO events (tenant_id, username, action, success, timestamp) "
                "VALUES (NULL, 'admin', 'login', 1, CURRENT_TIMESTAMP)"
            )
        )

    with SessionLocal() as db:
        result = upgrade.backfill_default_tenant(db)
        assert result.skipped is False

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        assert tenant is not None
        default_tenant_id = tenant.id
        memberships = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id)
            .order_by(Membership.user_id)
            .all()
        )
        assert len(memberships) == 2
        roles = {membership.user_id: membership.role for membership in memberships}
        assert roles[admin_id] == RoleEnum.OWNER
        assert roles[viewer_id] == RoleEnum.VIEWER

    with engine.connect() as conn:
        event_tenant_id = conn.execute(text("SELECT tenant_id FROM events LIMIT 1")).scalar()
        assert event_tenant_id == default_tenant_id

    with SessionLocal() as db:
        upgrade.backfill_default_tenant(db)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        assert tenant is not None
        memberships = db.query(Membership).filter(Membership.tenant_id == tenant.id).all()
        assert len(memberships) == 2


def test_event_backfill_assigns_default_tenant(db_setup):
    engine, SessionLocal = db_setup
    upgrade = load_backfill_module()

    with SessionLocal() as db:
        user = User(username="legacy", password_hash="x", role="admin")
        db.add(user)
        db.commit()

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE events"))
        conn.execute(
            text(
                "CREATE TABLE events ("
                "id INTEGER PRIMARY KEY, "
                "tenant_id INTEGER NULL, "
                "username VARCHAR, "
                "action VARCHAR NOT NULL, "
                "success BOOLEAN NOT NULL, "
                "timestamp DATETIME NOT NULL"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO events (tenant_id, username, action, success, timestamp) "
                "VALUES (NULL, 'legacy', 'login', 1, CURRENT_TIMESTAMP)"
            )
        )

    with SessionLocal() as db:
        result = upgrade.backfill_default_tenant(db)
        assert result.skipped is False
        default_tenant_id = result.tenant_id

    with engine.connect() as conn:
        event_tenant_id = conn.execute(text("SELECT tenant_id FROM events LIMIT 1")).scalar()
        assert event_tenant_id == default_tenant_id


def test_audit_backfill_default_tenant(db_setup):
    engine, SessionLocal = db_setup
    upgrade = load_backfill_module()

    with SessionLocal() as db:
        user = User(username="auditor", password_hash="x", role="admin")
        db.add(user)
        db.commit()

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE audit_logs"))
        conn.execute(
            text(
                "CREATE TABLE audit_logs ("
                "id INTEGER PRIMARY KEY, "
                "tenant_id INTEGER NULL, "
                "username VARCHAR, "
                "event VARCHAR NOT NULL, "
                "timestamp DATETIME NOT NULL"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO audit_logs (tenant_id, username, event, timestamp) "
                "VALUES (NULL, 'auditor', 'user_login_success', CURRENT_TIMESTAMP)"
            )
        )

    with SessionLocal() as db:
        result = upgrade.backfill_default_tenant(db)
        assert result.skipped is False
        default_tenant_id = result.tenant_id

    with engine.connect() as conn:
        audit_tenant_id = conn.execute(text("SELECT tenant_id FROM audit_logs LIMIT 1")).scalar()
        assert audit_tenant_id == default_tenant_id
