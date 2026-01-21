from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.keys import hash_secret
from app.core.security import get_password_hash
from app.core.utils.domain import normalize_domain
from app.crud.users import create_user, get_user_by_username
from app.crud.memberships import create_membership
from app.crud.websites import create_website as create_website_record
from app.models.api_keys import APIKey
from app.models.memberships import Membership
from app.models.plans import Plan
from app.models.users import User
from app.models.tenants import Tenant
from app.models.website_environments import WebsiteEnvironment
from app.models.websites import Website


def get_or_create_tenant(db: Session, slug: str, name: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if tenant:
        return tenant
    tenant = Tenant(slug=slug, name=name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def get_or_create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    user = get_user_by_username(db, username)
    if user:
        return user
    password_hash = get_password_hash(password)
    return create_user(db, username=username, password_hash=password_hash, role=role)


def get_or_create_membership(db: Session, user: User, tenant: Tenant, role: str) -> Membership:
    return create_membership(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        role=role,
        created_by_user_id=user.id,
        status="active",
    )


def get_or_create_website(
    db: Session,
    tenant: Tenant,
    domain: str,
    created_by_user_id: int | None = None,
) -> Website:
    normalized = normalize_domain(domain)
    website = (
        db.query(Website)
        .filter(Website.tenant_id == tenant.id, Website.domain == normalized)
        .first()
    )
    if website:
        return website
    return create_website_record(
        db,
        tenant.id,
        normalized,
        created_by_user_id=created_by_user_id,
    )


def get_environment_by_name(
    db: Session,
    website: Website,
    name: str = "production",
) -> WebsiteEnvironment | None:
    normalized = name.strip().lower()
    return (
        db.query(WebsiteEnvironment)
        .filter(
            WebsiteEnvironment.website_id == website.id,
            WebsiteEnvironment.name == normalized,
        )
        .first()
    )


def get_or_create_api_key(
    db: Session,
    *,
    tenant: Tenant,
    website: Website,
    environment: WebsiteEnvironment,
    public_key: str,
    raw_secret: str,
    name: str | None = None,
    revoked: bool = False,
) -> APIKey:
    api_key = db.query(APIKey).filter(APIKey.public_key == public_key).first()
    if api_key:
        if api_key.name != name:
            api_key.name = name
        if revoked and api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(timezone.utc)
            api_key.status = "revoked"
        if not revoked and api_key.revoked_at is not None:
            api_key.revoked_at = None
            api_key.status = "active"
        db.commit()
        db.refresh(api_key)
        return api_key
    api_key = APIKey(
        tenant_id=tenant.id,
        website_id=website.id,
        environment_id=environment.id,
        public_key=public_key,
        secret_hash=hash_secret(raw_secret),
        name=name,
        status="revoked" if revoked else "active",
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def get_or_create_plan(
    db: Session,
    *,
    name: str,
    price_monthly: float | None,
    limits_json: dict,
    features_json: dict,
    is_active: bool = True,
) -> Plan:
    plan = db.query(Plan).filter(Plan.name == name).first()
    if plan:
        plan.price_monthly = price_monthly
        plan.limits_json = limits_json
        plan.features_json = features_json
        plan.is_active = is_active
        db.commit()
        db.refresh(plan)
        return plan
    plan = Plan(
        name=name,
        price_monthly=price_monthly,
        limits_json=limits_json,
        features_json=features_json,
        is_active=is_active,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def seed_default_plans(db: Session) -> list[Plan]:
    defaults = [
        {
            "name": "Free",
            "price_monthly": 0,
            "limits_json": {
                "websites": 1,
                "events_per_month": 50000,
                "retention_days": 7,
                "geo_history_days": 1,
                "raw_ip_retention_days": 1,
                "notification_rules": 1,
                "ingest_rpm": 120,
                "ingest_burst": 120,
            },
            "features_json": {
                "heatmaps": False,
                "integrity_monitoring": True,
                "prescriptions": False,
                "advanced_alerting": False,
                "geo_map": False,
            },
        },
        {
            "name": "Starter",
            "price_monthly": 49,
            "limits_json": {
                "websites": 3,
                "events_per_month": 250000,
                "retention_days": 30,
                "geo_history_days": 7,
                "raw_ip_retention_days": 7,
                "notification_rules": 2,
                "ingest_rpm": 500,
                "ingest_burst": 500,
            },
            "features_json": {
                "heatmaps": True,
                "integrity_monitoring": True,
                "prescriptions": False,
                "advanced_alerting": False,
                "geo_map": False,
            },
        },
        {
            "name": "Pro",
            "price_monthly": 149,
            "limits_json": {
                "websites": 10,
                "events_per_month": 1000000,
                "retention_days": 90,
                "geo_history_days": 30,
                "raw_ip_retention_days": 30,
                "notification_rules": 10,
                "ingest_rpm": 2000,
                "ingest_burst": 2000,
            },
            "features_json": {
                "heatmaps": True,
                "integrity_monitoring": True,
                "prescriptions": True,
                "advanced_alerting": True,
                "geo_map": True,
            },
        },
        {
            "name": "Business",
            "price_monthly": 399,
            "limits_json": {
                "websites": 25,
                "events_per_month": 5000000,
                "retention_days": 180,
                "geo_history_days": 90,
                "raw_ip_retention_days": 90,
                "notification_rules": 25,
                "ingest_rpm": 5000,
                "ingest_burst": 5000,
            },
            "features_json": {
                "heatmaps": True,
                "integrity_monitoring": True,
                "prescriptions": True,
                "advanced_alerting": True,
                "priority_support": True,
                "geo_map": True,
            },
        },
    ]

    seeded: list[Plan] = []
    for plan in defaults:
        seeded.append(
            get_or_create_plan(
                db,
                name=plan["name"],
                price_monthly=plan["price_monthly"],
                limits_json=plan["limits_json"],
                features_json=plan["features_json"],
                is_active=True,
            )
        )
    return seeded
