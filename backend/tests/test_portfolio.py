import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./portfolio_test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.policy as policy_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.affiliates import create_partner  # noqa: E402
from app.crud.memberships import create_membership  # noqa: E402
from app.crud.resellers import create_managed_tenant, create_reseller_account  # noqa: E402
from app.crud.subscriptions import set_tenant_plan  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.websites import create_website  # noqa: E402
from app.crud.website_environments import list_environments  # noqa: E402
from app.models.enums import RoleEnum  # noqa: E402
from app.models.incidents import Incident  # noqa: E402
from app.models.partners import PartnerUser  # noqa: E402
from app.models.plans import Plan  # noqa: E402
from app.models.revenue_leaks import RevenueLeakEstimate  # noqa: E402
from app.models.trust_scoring import TrustSnapshot  # noqa: E402


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


def _login(username: str, tenant_slug: str | None = None) -> str:
    headers = {"X-Tenant-ID": tenant_slug} if tenant_slug else None
    resp = client.post(
        "/login",
        json={"username": username, "password": "pw"},
        headers=headers,
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
        return tenant, user, website, env


def _seed_plan(db, *, name: str, portfolio_view: bool, portfolio_exports: bool) -> Plan:
    plan = Plan(
        name=name,
        price_monthly=199,
        limits_json={"retention_days": 30},
        features_json={
            "portfolio_view": portfolio_view,
            "portfolio_exports": portfolio_exports,
        },
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _add_portfolio_data(
    db,
    *,
    tenant_id: int,
    website_id: int,
    env_id: int,
    trust_score: int,
    lost_revenue: float,
    incident_severity: str,
):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    db.add(
        TrustSnapshot(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            bucket_start=now,
            path=None,
            trust_score=trust_score,
            confidence=0.8,
            factor_count=2,
        )
    )
    db.add(
        RevenueLeakEstimate(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            bucket_start=now,
            path="/checkout",
            baseline_conversion_rate=0.2,
            observed_conversion_rate=0.05,
            sessions_in_bucket=100,
            expected_conversions=20,
            observed_conversions=5,
            lost_conversions=15,
            revenue_per_conversion=100.0,
            estimated_lost_revenue=lost_revenue,
            linked_trust_score=trust_score,
            confidence=0.7,
        )
    )
    db.add(
        Incident(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=env_id,
            status="open",
            category="security",
            title="Credential stuffing surge",
            summary="High failure rates",
            severity=incident_severity,
            first_seen_at=now - timedelta(hours=2),
            last_seen_at=now,
        )
    )


def test_portfolio_summary_scoped_to_tenant_or_managed_tenants():
    db_url = f"sqlite:///./portfolio_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    tenant_a, user_a, website_a, env_a = _seed_tenant(
        SessionLocal,
        username="alice",
        tenant_name="Acme",
        domain="acme.example.com",
    )
    tenant_b, _user_b, website_b, env_b = _seed_tenant(
        SessionLocal,
        username="bob",
        tenant_name="Umbrella",
        domain="umbrella.example.com",
    )

    with SessionLocal() as db:
        plan = _seed_plan(db, name="Business", portfolio_view=True, portfolio_exports=False)
        set_tenant_plan(db, tenant_a.id, plan.id)
        set_tenant_plan(db, tenant_b.id, plan.id)
        _add_portfolio_data(
            db,
            tenant_id=tenant_a.id,
            website_id=website_a.id,
            env_id=env_a.id,
            trust_score=88,
            lost_revenue=1200.0,
            incident_severity="critical",
        )
        _add_portfolio_data(
            db,
            tenant_id=tenant_b.id,
            website_id=website_b.id,
            env_id=env_b.id,
            trust_score=55,
            lost_revenue=350.0,
            incident_severity="high",
        )
        db.commit()

    token = _login("alice", tenant_a.slug)
    resp = client.get(
        "/api/v1/portfolio/summary",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_a.slug},
    )
    assert resp.status_code == 200
    payload = resp.json()["summary"]
    assert payload["website_count"] == 1
    assert payload["open_incidents_total"] == 1

    with SessionLocal() as db:
        partner_user = create_user(db, username="reseller", password_hash=get_password_hash("pw"))
        partner = create_partner(
            db,
            name="Reseller",
            code="reseller",
            status="active",
            commission_type="flat",
            commission_value=10,
        )
        db.add(PartnerUser(partner_id=partner.id, user_id=partner_user.id, role="reseller_admin"))
        create_reseller_account(db, partner_id=partner.id, billing_mode="customer_pays_stripe")
        create_managed_tenant(db, partner_id=partner.id, tenant_id=tenant_a.id, status="active")
        db.commit()

    reseller_token = _login("reseller")
    reseller_resp = client.get(
        "/api/v1/portfolio/summary",
        params={"tenant_id": tenant_a.id},
        headers={"Authorization": f"Bearer {reseller_token}"},
    )
    assert reseller_resp.status_code == 200
    reseller_payload = reseller_resp.json()["summary"]
    assert reseller_payload["website_count"] == 1

    blocked_resp = client.get(
        "/api/v1/portfolio/summary",
        params={"tenant_id": tenant_b.id},
        headers={"Authorization": f"Bearer {reseller_token}"},
    )
    assert blocked_resp.status_code == 404


def test_portfolio_export_redacts_sensitive_fields():
    db_url = f"sqlite:///./portfolio_export_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    tenant, _user, website, env = _seed_tenant(
        SessionLocal,
        username="carol",
        tenant_name="Wayne",
        domain="wayne.example.com",
    )

    with SessionLocal() as db:
        plan = _seed_plan(db, name="Enterprise", portfolio_view=True, portfolio_exports=True)
        set_tenant_plan(db, tenant.id, plan.id)
        _add_portfolio_data(
            db,
            tenant_id=tenant.id,
            website_id=website.id,
            env_id=env.id,
            trust_score=92,
            lost_revenue=500.0,
            incident_severity="medium",
        )
        db.commit()

    token = _login("carol", tenant.slug)
    resp = client.get(
        "/api/v1/portfolio/export",
        params={"format": "json"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant.slug},
    )
    assert resp.status_code == 200
    payload_text = resp.text.lower()
    assert "secret" not in payload_text
    assert "client_ip" not in payload_text
