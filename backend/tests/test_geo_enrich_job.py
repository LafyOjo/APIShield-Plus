import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.core.privacy import hash_ip
from app.core.time import utcnow
from app.crud.tenants import create_tenant
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.geo.provider import GeoResult
from app.jobs import geo_enrich as geo_job
from app.models.alerts import Alert
from app.models.behaviour_events import BehaviourEvent
from app.models.ip_enrichments import IPEnrichment


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _seed_event_and_alert(db, *, tenant_id: int, website_id: int, env_id: int, ip: str, ip_hash: str):
    event = BehaviourEvent(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        ingested_at=utcnow(),
        event_ts=datetime.now(timezone.utc),
        event_id=str(uuid4()),
        event_type="page_view",
        url="https://example.com/",
        path="/",
        ip_hash=ip_hash,
    )
    db.add(event)
    alert = Alert(
        tenant_id=tenant_id,
        ip_address=ip,
        ip_hash=ip_hash,
        client_ip=ip,
        total_fails=1,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.commit()


def test_geo_enrich_job_creates_enrichment_records_from_recent_events(monkeypatch):
    db_url = f"sqlite:///./geo_job_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    class StubProvider:
        def lookup(self, ip_str: str):
            return GeoResult(country_code="US", city="Boulder")

    import app.geo.enrichment as enrichment_module

    monkeypatch.setattr(enrichment_module, "get_geo_provider", lambda: StubProvider())

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip = "203.0.113.10"
        ip_hash = hash_ip(tenant.id, ip)
        _seed_event_and_alert(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            ip=ip,
            ip_hash=ip_hash,
        )
        geo_job.run_geo_enrichment(db, lookback_minutes=60, max_items=10)
        record = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant.id, IPEnrichment.ip_hash == ip_hash)
            .first()
        )
        assert record is not None
        assert record.country_code == "US"
        assert record.lookup_status == "ok"


def test_geo_enrich_job_respects_lookup_limit(monkeypatch):
    db_url = f"sqlite:///./geo_job_limit_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    class StubProvider:
        def lookup(self, ip_str: str):
            return GeoResult(country_code="US")

    import app.geo.enrichment as enrichment_module

    monkeypatch.setattr(enrichment_module, "get_geo_provider", lambda: StubProvider())

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip_hashes = []
        for idx in range(2):
            ip = f"203.0.113.{10 + idx}"
            ip_hash = hash_ip(tenant.id, ip)
            ip_hashes.append(ip_hash)
            _seed_event_and_alert(
                db,
                tenant_id=tenant.id,
                website_id=website.id,
                env_id=env.id,
                ip=ip,
                ip_hash=ip_hash,
            )
        processed = geo_job.run_geo_enrichment(db, lookback_minutes=60, max_items=1)
        assert processed == 1
        ok_count = db.query(IPEnrichment).filter(IPEnrichment.lookup_status == "ok").count()
        assert ok_count == 1


def test_geo_enrich_job_handles_provider_failure_gracefully(monkeypatch):
    db_url = f"sqlite:///./geo_job_fail_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    class StubProvider:
        def lookup(self, ip_str: str):
            raise RuntimeError("provider down")

    import app.geo.enrichment as enrichment_module

    monkeypatch.setattr(enrichment_module, "get_geo_provider", lambda: StubProvider())

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip = "203.0.113.99"
        ip_hash = hash_ip(tenant.id, ip)
        _seed_event_and_alert(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            ip=ip,
            ip_hash=ip_hash,
        )
        processed = geo_job.run_geo_enrichment(db, lookback_minutes=60, max_items=10)
        assert processed == 1
        record = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant.id, IPEnrichment.ip_hash == ip_hash)
            .first()
        )
        assert record is not None
        assert record.lookup_status == "failed"
