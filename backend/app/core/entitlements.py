from typing import Any

from sqlalchemy.orm import Session

from app.models.feature_entitlements import FeatureEntitlement
from app.models.plans import Plan


ALLOWED_FEATURES = {
    "heatmaps",
    "integrity_monitoring",
    "prescriptions",
    "advanced_alerting",
    "priority_support",
    "geo_map",
}

ALLOWED_ENTITLEMENT_SOURCES = {
    "plan",
    "manual_override",
    "trial",
    "promotion",
}

def invalidate_entitlement_cache(tenant_id: int) -> None:
    from app.entitlements.resolver import invalidate_entitlement_cache as invalidate_cache

    invalidate_cache(tenant_id)


def resolve_entitlements(plan: Plan) -> dict:
    return get_plan_defaults(plan)


def validate_feature(feature: str) -> None:
    if feature not in ALLOWED_FEATURES:
        raise ValueError(f"Unsupported feature: {feature}")


def validate_entitlement_source(source: str) -> None:
    if source not in ALLOWED_ENTITLEMENT_SOURCES:
        raise ValueError(f"Unsupported entitlement source: {source}")


def get_tenant_plan(db: Session, tenant_id: int) -> Plan | None:
    from app.crud.plans import get_plan_by_name
    from app.crud.subscriptions import get_active_subscription_for_tenant

    subscription = get_active_subscription_for_tenant(db, tenant_id)
    if subscription:
        if subscription.plan is not None:
            return subscription.plan
        plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if plan:
            return plan
    return get_plan_by_name(db, "Free")


def get_plan_defaults(plan: Plan | None) -> dict[str, dict[str, Any]]:
    features = {feature: False for feature in ALLOWED_FEATURES}
    limits: dict[str, Any] = {}
    if plan:
        limits = plan.limits_json or {}
        for feature, enabled in (plan.features_json or {}).items():
            if feature in ALLOWED_FEATURES:
                features[feature] = bool(enabled)
    return {"features": features, "limits": limits}


def get_overrides(db: Session, tenant_id: int) -> list[FeatureEntitlement]:
    return (
        db.query(FeatureEntitlement)
        .filter(FeatureEntitlement.tenant_id == tenant_id)
        .order_by(FeatureEntitlement.feature)
        .all()
    )


def resolve_effective_entitlements(
    db: Session,
    tenant_id: int,
    *,
    use_cache: bool = True,
) -> dict[str, dict[str, Any]]:
    from app.entitlements.resolver import resolve_entitlements_for_tenant

    return resolve_entitlements_for_tenant(db, tenant_id, use_cache=use_cache)


def get_effective_entitlements(db: Session, tenant_id: int) -> list[dict]:
    plan = get_tenant_plan(db, tenant_id)
    defaults = get_plan_defaults(plan)
    entitlements: dict[str, dict[str, Any]] = {}
    if plan:
        for feature, enabled in defaults["features"].items():
            entitlements[feature] = {
                "feature": feature,
                "enabled": bool(enabled),
                "source": "plan",
                "source_plan_id": plan.id,
            }
    overrides = get_overrides(db, tenant_id)
    for entitlement in overrides:
        entitlements[entitlement.feature] = {
            "feature": entitlement.feature,
            "enabled": entitlement.enabled,
            "source": entitlement.source,
            "source_plan_id": entitlement.source_plan_id,
        }
    return [entitlements[key] for key in sorted(entitlements.keys())]


def build_tenant_context_snapshot(db: Session, tenant_id: int) -> dict[str, Any]:
    entitlements = resolve_effective_entitlements(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "plan_name": entitlements.get("plan_name"),
        "features": entitlements["features"],
        "limits": entitlements["limits"],
        "usage": None,
    }


def assert_can_create_website(db: Session, tenant_id: int) -> bool:
    from app.models.enums import WebsiteStatusEnum
    from app.models.websites import Website
    from app.entitlements.enforcement import assert_limit

    entitlements = resolve_effective_entitlements(db, tenant_id)
    limits = entitlements.get("limits", {}) if entitlements else {}
    limit_value = limits.get("websites")
    try:
        max_websites = int(limit_value)
    except (TypeError, ValueError):
        max_websites = None
    if not max_websites:
        return True
    current = (
        db.query(Website)
        .filter(
            Website.tenant_id == tenant_id,
            Website.status != WebsiteStatusEnum.DELETED,
            Website.deleted_at.is_(None),
        )
        .count()
    )
    assert_limit(entitlements, "websites", current, mode="hard")
    return True
