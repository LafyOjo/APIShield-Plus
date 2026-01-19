import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.privacy import hash_ip
from app.core.security import get_password_hash
from app.crud.memberships import create_membership
from app.crud.subscriptions import set_tenant_plan
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.website_environments import list_environments
from app.crud.websites import create_website
from app.models.alerts import Alert
from app.models.enums import RoleEnum
from app.models.geo_event_aggs import GeoEventAgg
from app.models.ip_enrichments import IPEnrichment
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
    db_module.Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str, tenant_slug: str) -> str:
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers={"X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _seed_tenant(SessionLocal, *, username: str, tenant_name: str, domain: str):
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
        website = create_website(db, tenant.id, domain, created_by_user_id=user.id)
        env = list_environments(db, website.id)[0]
        db.commit()
        return tenant.slug, tenant.id, user.id, website.id, env.id


def _set_plan(db, *, tenant_id: int, name: str, geo_map: bool, geo_days: int):
    plan = Plan(
        name=name,
        price_monthly=99,
        limits_json={"geo_history_days": geo_days},
        features_json={"geo_map": geo_map},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    set_tenant_plan(db, tenant_id, plan.id)


def _add_geo_agg(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    bucket_start: datetime,
    country_code: str,
    city: str | None,
    lat: float | None,
    lon: float | None,
    count: int,
):
    if bucket_start.tzinfo is not None:
        bucket_start = bucket_start.astimezone(timezone.utc).replace(tzinfo=None)
    db.add(
        GeoEventAgg(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            bucket_start=bucket_start,
            event_category="behaviour",
            severity=None,
            country_code=country_code,
            region="CO",
            city=city,
            latitude=lat,
            longitude=lon,
            asn_number=64512,
            asn_org="Example ASN",
            is_datacenter=False,
            count=count,
        )
    )


def test_map_summary_tenant_scoped():
    db_url = f"sqlite:///./map_summary_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_a_slug, tenant_a_id, _user_a_id, website_a_id, env_a_id = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        domain="a.example.com",
    )
    tenant_b_slug, tenant_b_id, _user_b_id, website_b_id, env_b_id = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="Umbrella",
        domain="b.example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_a_id, name="GeoProA", geo_map=True, geo_days=7)
        _set_plan(db, tenant_id=tenant_b_id, name="GeoProB", geo_map=True, geo_days=7)
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _add_geo_agg(
            db,
            tenant_id=tenant_a_id,
            website_id=website_a_id,
            env_id=env_a_id,
            bucket_start=now,
            country_code="US",
            city="Boulder",
            lat=40.0,
            lon=-105.0,
            count=5,
        )
        _add_geo_agg(
            db,
            tenant_id=tenant_b_id,
            website_id=website_b_id,
            env_id=env_b_id,
            bucket_start=now,
            country_code="DE",
            city="Berlin",
            lat=52.5,
            lon=13.4,
            count=3,
        )
        db.commit()

    token = _login("alice", tenant_a_slug)
    resp = client.get(
        "/api/v1/map/summary",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    codes = {item["country_code"] for item in payload["items"]}
    assert "US" in codes
    assert "DE" not in codes


def test_map_summary_clamps_time_range_by_entitlement():
    db_url = f"sqlite:///./map_summary_clamp_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="carol",
        tenant_name="Wayne",
        domain="example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_id, name="GeoProC", geo_map=True, geo_days=1)
        recent = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        old = recent - timedelta(days=5)
        _add_geo_agg(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            bucket_start=old,
            country_code="FR",
            city="Paris",
            lat=48.8,
            lon=2.3,
            count=10,
        )
        _add_geo_agg(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            bucket_start=recent,
            country_code="US",
            city="Denver",
            lat=39.7,
            lon=-104.9,
            count=2,
        )
        db.commit()

    token = _login("carol", tenant_slug)
    resp = client.get(
        "/api/v1/map/summary",
        params={"from": (datetime.utcnow() - timedelta(days=30)).isoformat()},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    codes = {item["country_code"] for item in payload["items"]}
    assert "US" in codes
    assert "FR" not in codes


def test_map_drilldown_does_not_return_raw_ip():
    db_url = f"sqlite:///./map_drilldown_ip_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="diana",
        tenant_name="Star",
        domain="example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_id, name="GeoProD", geo_map=True, geo_days=7)
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        ip = "203.0.113.25"
        ip_hash = hash_ip(tenant_id, ip)
        db.add(
            IPEnrichment(
                tenant_id=tenant_id,
                ip_hash=ip_hash,
                first_seen_at=now,
                last_seen_at=now,
                last_lookup_at=now,
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
        )
        db.add(
            Alert(
                tenant_id=tenant_id,
                ip_address=ip,
                ip_hash=ip_hash,
                client_ip=ip,
                total_fails=1,
                request_path="/login",
                timestamp=now,
            )
        )
        _add_geo_agg(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            bucket_start=now,
            country_code="US",
            city="Boulder",
            lat=40.0,
            lon=-105.0,
            count=1,
        )
        db.commit()

    token = _login("diana", tenant_slug)
    resp = client.get(
        "/api/v1/map/drilldown",
        params={"category": "threat", "country_code": "US"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ip_hashes"]
    assert "client_ip" not in payload["ip_hashes"][0]
    assert payload["ip_hashes"][0]["ip_hash"] == ip_hash


def test_map_endpoints_require_geo_map_feature_or_limit_view():
    db_url = f"sqlite:///./map_summary_free_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    tenant_slug, tenant_id, _user_id, website_id, env_id = _seed_tenant(
        SessionLocal,
        username="edward",
        tenant_name="Gotham",
        domain="example.com",
    )
    with SessionLocal() as db:
        _set_plan(db, tenant_id=tenant_id, name="FreeGeo", geo_map=False, geo_days=7)
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        _add_geo_agg(
            db,
            tenant_id=tenant_id,
            website_id=website_id,
            env_id=env_id,
            bucket_start=now,
            country_code="US",
            city="Denver",
            lat=39.7,
            lon=-104.9,
            count=1,
        )
        db.commit()

    token = _login("edward", tenant_slug)
    resp = client.get(
        "/api/v1/map/summary",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"]
    assert payload["items"][0]["city"] is None
    assert payload["items"][0]["latitude"] is None

    resp = client.get(
        "/api/v1/map/drilldown",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_slug},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["countries"]
    assert payload["cities"] == []
    assert payload["asns"] == []
    assert payload["ip_hashes"] == []
