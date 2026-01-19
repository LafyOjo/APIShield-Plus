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
from app.jobs import geo_aggregate as geo_job
from app.models.behaviour_events import BehaviourEvent
from app.models.geo_event_aggs import GeoEventAgg
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


def _seed_event(db, *, tenant_id: int, website_id: int, env_id: int, ip_hash: str):
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


def _seed_enrichment(db, *, tenant_id: int, ip_hash: str):
    record = IPEnrichment(
        tenant_id=tenant_id,
        ip_hash=ip_hash,
        first_seen_at=utcnow(),
        last_seen_at=utcnow(),
        last_lookup_at=utcnow(),
        lookup_status="ok",
        country_code="US",
        region="CO",
        city="Boulder",
        latitude=40.0,
        longitude=-105.0,
        asn_number=64512,
        asn_org="Example ASN",
        is_datacenter=False,
        source="local",
    )
    db.add(record)


def test_geo_aggregate_creates_bucketed_counts(monkeypatch):
    db_url = f"sqlite:///./geo_agg_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    monkeypatch.setattr(
        geo_job,
        "resolve_effective_entitlements",
        lambda db, tenant_id: {"features": {"geo_map": True}, "limits": {}},
    )

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip = "203.0.113.10"
        ip_hash = hash_ip(tenant.id, ip)
        _seed_enrichment(db, tenant_id=tenant.id, ip_hash=ip_hash)
        _seed_event(db, tenant_id=tenant.id, website_id=website.id, env_id=env.id, ip_hash=ip_hash)
        db.commit()

        updated = geo_job.run_geo_aggregate(db, lookback_minutes=60, max_buckets=10)
        assert updated == 1
        agg = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant.id).first()
        assert agg is not None
        assert agg.count == 1
        assert agg.event_category == "behaviour"
        assert agg.country_code == "US"


def test_geo_aggregate_tenant_scoped(monkeypatch):
    db_url = f"sqlite:///./geo_agg_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    monkeypatch.setattr(
        geo_job,
        "resolve_effective_entitlements",
        lambda db, tenant_id: {"features": {"geo_map": True}, "limits": {}},
    )

    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        website_a = create_website(db, tenant_a.id, "a.example.com")
        website_b = create_website(db, tenant_b.id, "b.example.com")
        env_a = list_environments(db, website_a.id)[0]
        env_b = list_environments(db, website_b.id)[0]
        ip_hash_a = hash_ip(tenant_a.id, "203.0.113.11")
        ip_hash_b = hash_ip(tenant_b.id, "203.0.113.12")
        _seed_enrichment(db, tenant_id=tenant_a.id, ip_hash=ip_hash_a)
        _seed_enrichment(db, tenant_id=tenant_b.id, ip_hash=ip_hash_b)
        _seed_event(db, tenant_id=tenant_a.id, website_id=website_a.id, env_id=env_a.id, ip_hash=ip_hash_a)
        _seed_event(db, tenant_id=tenant_b.id, website_id=website_b.id, env_id=env_b.id, ip_hash=ip_hash_b)
        db.commit()

        geo_job.run_geo_aggregate(db, lookback_minutes=60, max_buckets=10)
        count_a = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant_a.id).count()
        count_b = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant_b.id).count()
        assert count_a == 1
        assert count_b == 1


def test_geo_aggregate_country_only_mode_for_free_plan(monkeypatch):
    db_url = f"sqlite:///./geo_agg_free_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    monkeypatch.setattr(
        geo_job,
        "resolve_effective_entitlements",
        lambda db, tenant_id: {"features": {"geo_map": False}, "limits": {}},
    )

    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        website = create_website(db, tenant.id, "example.com")
        env = list_environments(db, website.id)[0]
        ip_hash = hash_ip(tenant.id, "203.0.113.13")
        _seed_enrichment(db, tenant_id=tenant.id, ip_hash=ip_hash)
        _seed_event(db, tenant_id=tenant.id, website_id=website.id, env_id=env.id, ip_hash=ip_hash)
        db.commit()

        geo_job.run_geo_aggregate(db, lookback_minutes=60, max_buckets=10)
        agg = db.query(GeoEventAgg).filter(GeoEventAgg.tenant_id == tenant.id).first()
        assert agg is not None
        assert agg.country_code == "US"
        assert agg.city is None
        assert agg.latitude is None
        assert agg.asn_number is None
