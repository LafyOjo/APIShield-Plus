import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

import app.core.db as db_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402


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


def test_tenant_default_data_region_set():
    db_url = f"sqlite:///./tenant_region_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    expected = settings.DEFAULT_TENANT_REGION or "us"
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Region Default")
        assert tenant.data_region == expected
        assert tenant.created_region == expected
        assert tenant.allowed_regions == [expected]
