import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.core.db import Base
import app.core.db as db_module
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.jobs.seed_demo_data import seed_demo_data
from app.models.enums import RoleEnum
from app.models.geo_event_aggs import GeoEventAgg
from app.models.incidents import Incident
from app.models.tenant_usage import TenantUsage


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_demo_seed_creates_incidents_and_geo_agg(tmp_path):
    db_url = f"sqlite:///{tmp_path}/demo_seed_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="demo-owner", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="DemoTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        result = seed_demo_data(db, tenant_id=tenant.id, created_by_user_id=owner.id, force=True)
        assert result.counts.get("incidents", 0) > 0
        assert result.counts.get("geo_event_aggs", 0) > 0
        assert (
            db.query(Incident)
            .filter(Incident.tenant_id == tenant.id, Incident.is_demo.is_(True))
            .count()
            > 0
        )
        assert (
            db.query(GeoEventAgg)
            .filter(GeoEventAgg.tenant_id == tenant.id, GeoEventAgg.is_demo.is_(True))
            .count()
            > 0
        )


def test_demo_data_excluded_from_usage_metering(tmp_path):
    db_url = f"sqlite:///{tmp_path}/demo_usage_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        owner = create_user(db, username="demo-owner-usage", password_hash=get_password_hash("pw"), role="user")
        tenant = create_tenant(db, name="DemoUsageTenant")
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=owner.id,
            role=RoleEnum.OWNER,
            created_by_user_id=owner.id,
        )
        seed_demo_data(db, tenant_id=tenant.id, created_by_user_id=owner.id, force=True)
        assert db.query(TenantUsage).count() == 0
