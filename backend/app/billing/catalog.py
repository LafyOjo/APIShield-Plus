from typing import Optional

from app.core.config import settings


_PLAN_NAME_MAP = {
    "free": "Free",
    "pro": "Pro",
    "business": "Business",
    "enterprise": "Enterprise",
    "starter": "Starter",
}

PLAN_TIERS = {
    "free": {
        "plan_name": "Free",
        "price_monthly": 0,
        "limits": {
            "websites": 1,
            "events_per_month": 50000,
            "retention_days": 7,
            "raw_event_retention_days": 7,
            "geo_history_days": 1,
            "aggregate_retention_days": 1,
            "geo_granularity": "country",
            "raw_ip_retention_days": 1,
            "notification_channels": 1,
            "notification_rules": 1,
            "ingest_rpm": 120,
            "ingest_burst": 120,
        },
        "features": {
            "trust_score": True,
            "integrity_monitoring": True,
            "geo_map": True,
            "advanced_alerting": False,
            "prescriptions": False,
            "revenue_leaks": False,
            "remediation_workspace": False,
            "verification": False,
            "incident_exports": False,
            "data_exports": False,
            "portfolio_view": False,
            "portfolio_exports": False,
            "sso_oidc": False,
            "sso_saml": False,
            "scim": False,
            "role_templates": False,
            "legal_hold": False,
            "priority_support": False,
        },
    },
    "pro": {
        "plan_name": "Pro",
        "price_monthly": 249,
        "limits": {
            "websites": 10,
            "events_per_month": 1000000,
            "retention_days": 30,
            "raw_event_retention_days": 30,
            "geo_history_days": 30,
            "aggregate_retention_days": 30,
            "geo_granularity": "city",
            "raw_ip_retention_days": 30,
            "notification_channels": 10,
            "notification_rules": 10,
            "ingest_rpm": 2000,
            "ingest_burst": 2000,
        },
        "features": {
            "trust_score": True,
            "integrity_monitoring": True,
            "geo_map": True,
            "advanced_alerting": False,
            "prescriptions": True,
            "revenue_leaks": True,
            "remediation_workspace": True,
            "verification": True,
            "incident_exports": True,
            "data_exports": False,
            "portfolio_view": False,
            "portfolio_exports": False,
            "sso_oidc": False,
            "sso_saml": False,
            "scim": False,
            "role_templates": False,
            "legal_hold": False,
            "priority_support": False,
            "audit_export_ip_hash": False,
        },
    },
    "business": {
        "plan_name": "Business",
        "price_monthly": 399,
        "limits": {
            "websites": 25,
            "events_per_month": 5000000,
            "retention_days": 180,
            "raw_event_retention_days": 180,
            "geo_history_days": 90,
            "aggregate_retention_days": 90,
            "geo_granularity": "asn",
            "raw_ip_retention_days": 90,
            "notification_channels": 25,
            "notification_rules": 25,
            "ingest_rpm": 5000,
            "ingest_burst": 5000,
        },
        "features": {
            "trust_score": True,
            "integrity_monitoring": True,
            "geo_map": True,
            "advanced_alerting": True,
            "prescriptions": True,
            "revenue_leaks": True,
            "remediation_workspace": True,
            "verification": True,
            "incident_exports": True,
            "data_exports": True,
            "portfolio_view": True,
            "portfolio_exports": False,
            "sso_oidc": True,
            "sso_saml": False,
            "scim": False,
            "role_templates": True,
            "legal_hold": False,
            "priority_support": True,
            "audit_export_ip_hash": True,
        },
    },
    "enterprise": {
        "plan_name": "Enterprise",
        "price_monthly": None,
        "limits": {
            "websites": None,
            "events_per_month": None,
            "retention_days": 365,
            "raw_event_retention_days": 365,
            "geo_history_days": 180,
            "aggregate_retention_days": 180,
            "geo_granularity": "asn",
            "raw_ip_retention_days": 180,
            "notification_channels": None,
            "notification_rules": None,
            "ingest_rpm": None,
            "ingest_burst": None,
        },
        "features": {
            "trust_score": True,
            "integrity_monitoring": True,
            "geo_map": True,
            "advanced_alerting": True,
            "prescriptions": True,
            "revenue_leaks": True,
            "remediation_workspace": True,
            "verification": True,
            "incident_exports": True,
            "data_exports": True,
            "portfolio_view": True,
            "portfolio_exports": True,
            "sso_oidc": True,
            "sso_saml": True,
            "scim": True,
            "role_templates": True,
            "legal_hold": True,
            "priority_support": True,
            "audit_export_ip_hash": True,
        },
    },
}


def get_plan_tiers() -> dict[str, dict[str, object]]:
    return {key: dict(value) for key, value in PLAN_TIERS.items()}


def normalize_plan_key(value: str | None) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def plan_key_from_plan_name(plan_name: str | None) -> Optional[str]:
    if not plan_name:
        return None
    normalized = plan_name.strip().lower()
    for key, name in _PLAN_NAME_MAP.items():
        if name.lower() == normalized:
            return key
    return normalized


def get_plan_name(plan_key: str) -> Optional[str]:
    normalized = normalize_plan_key(plan_key)
    if not normalized:
        return None
    return _PLAN_NAME_MAP.get(normalized)


def get_plan_catalog() -> dict[str, dict[str, Optional[str]]]:
    return {
        "free": {"plan_name": "Free", "price_id": None},
        "pro": {"plan_name": "Pro", "price_id": settings.STRIPE_PRICE_ID_PRO},
        "business": {"plan_name": "Business", "price_id": settings.STRIPE_PRICE_ID_BUSINESS},
        "enterprise": {"plan_name": "Enterprise", "price_id": settings.STRIPE_PRICE_ID_ENTERPRISE},
    }


def get_price_id(plan_key: str) -> Optional[str]:
    catalog = get_plan_catalog()
    entry = catalog.get(normalize_plan_key(plan_key) or "")
    return entry.get("price_id") if entry else None


def plan_key_from_price_id(price_id: str | None) -> Optional[str]:
    if not price_id:
        return None
    catalog = get_plan_catalog()
    for key, entry in catalog.items():
        if entry.get("price_id") == price_id:
            return key
    return None
