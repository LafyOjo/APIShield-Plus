import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

import app.core.db as db_module
from app.core.config import settings
from app.core.time import utcnow
from app.crud.tenants import create_tenant
from app.geo import enrichment as enrichment_module
from app.geo.enrichment import get_or_lookup_enrichment, mark_ip_seen
from app.geo.provider import GeoResult
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


def test_ip_enrichment_upsert_unique_per_tenant():
    db_url = f"sqlite:///./ip_enrich_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        mark_ip_seen(db, tenant_a.id, "hash-123")
        mark_ip_seen(db, tenant_a.id, "hash-123")
        mark_ip_seen(db, tenant_b.id, "hash-123")
        count_a = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant_a.id, IPEnrichment.ip_hash == "hash-123")
            .count()
        )
        count_b = (
            db.query(IPEnrichment)
            .filter(IPEnrichment.tenant_id == tenant_b.id, IPEnrichment.ip_hash == "hash-123")
            .count()
        )
        assert count_a == 1
        assert count_b == 1


def test_ip_enrichment_dedupes_repeated_lookups(monkeypatch):
    db_url = f"sqlite:///./ip_enrich_dedupe_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")

        class StubProvider:
            def __init__(self):
                self.calls = 0

            def lookup(self, ip_str: str):
                self.calls += 1
                return GeoResult(country_code="US", city="Denver")

        stub = StubProvider()
        monkeypatch.setattr(enrichment_module, "get_geo_provider", lambda: stub)
        monkeypatch.setattr(settings, "GEO_ENRICHMENT_TTL_DAYS", 30)
        first = get_or_lookup_enrichment(
            db,
            tenant_id=tenant.id,
            ip_hash="hash-456",
            client_ip="8.8.8.8",
        )
        second = get_or_lookup_enrichment(
            db,
            tenant_id=tenant.id,
            ip_hash="hash-456",
            client_ip="8.8.8.8",
        )
        assert first.id == second.id
        assert stub.calls == 1


def test_ip_enrichment_updates_last_seen_at():
    db_url = f"sqlite:///./ip_enrich_seen_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Tenant A")
        record = mark_ip_seen(db, tenant.id, "hash-789")
        previous = record.last_seen_at
        record.last_seen_at = utcnow() - timedelta(days=1)
        db.commit()
        refreshed = get_or_lookup_enrichment(
            db,
            tenant_id=tenant.id,
            ip_hash="hash-789",
            client_ip=None,
        )
        assert refreshed.last_seen_at != previous
