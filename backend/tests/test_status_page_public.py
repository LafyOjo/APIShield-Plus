import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.policy as policy_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.crud.status_page import create_status_incident  # noqa: E402
from app.models.enums import StatusImpactEnum, StatusIncidentStatusEnum  # noqa: E402


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
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_status_page_public_endpoints_accessible_without_auth():
    db_url = f"sqlite:///./status_public_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    with SessionLocal() as db:
        create_status_incident(
            db,
            title="API latency issues",
            status=StatusIncidentStatusEnum.IDENTIFIED,
            impact_level=StatusImpactEnum.MAJOR,
            components_affected=["api"],
            message="We are investigating elevated latency.",
            is_published=True,
        )
        create_status_incident(
            db,
            title="Internal draft",
            status=StatusIncidentStatusEnum.INVESTIGATING,
            impact_level=StatusImpactEnum.MINOR,
            components_affected=["dashboard"],
            message="Internal note",
            is_published=False,
        )

    resp = client.get("/api/status/components")
    assert resp.status_code == 200
    components = resp.json()
    keys = {row["key"] for row in components}
    assert "api" in keys
    assert "ingest" in keys

    resp = client.get("/api/status/incidents")
    assert resp.status_code == 200
    incidents = resp.json()
    assert len(incidents) == 1
    assert incidents[0]["title"] == "API latency issues"
