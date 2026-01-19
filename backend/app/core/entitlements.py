from typing import Any
import time

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

ENTITLEMENT_CACHE_TTL_SECONDS = 30
_ENTITLEMENT_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}


def _get_cached_entitlements(tenant_id: int) -> dict[str, Any] | None:
    cached = _ENTITLEMENT_CACHE.get(tenant_id)
    if not cached:
        return None
    expires_at, payload = cached
    if time.monotonic() > expires_at:
        _ENTITLEMENT_CACHE.pop(tenant_id, None)
        return None
    return payload


def _set_cached_entitlements(tenant_id: int, payload: dict[str, Any]) -> None:
    _ENTITLEMENT_CACHE[tenant_id] = (time.monotonic() + ENTITLEMENT_CACHE_TTL_SECONDS, payload)


def invalidate_entitlement_cache(tenant_id: int) -> None:
    _ENTITLEMENT_CACHE.pop(tenant_id, None)


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
    if use_cache:
        cached = _get_cached_entitlements(tenant_id)
        if cached is not None:
            return cached
    plan = get_tenant_plan(db, tenant_id)
    defaults = get_plan_defaults(plan)
    features = dict(defaults["features"])
    overrides = get_overrides(db, tenant_id)
    for entitlement in overrides:
        if entitlement.feature in ALLOWED_FEATURES:
            features[entitlement.feature] = bool(entitlement.enabled)
    payload = {"features": features, "limits": defaults["limits"]}
    if use_cache:
        _set_cached_entitlements(tenant_id, payload)
    return payload


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
    plan = get_tenant_plan(db, tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "plan_name": plan.name if plan else None,
        "features": entitlements["features"],
        "limits": entitlements["limits"],
        "usage": None,
    }


def assert_can_create_website(tenant_id: int) -> bool:
    _ = tenant_id
    return True
