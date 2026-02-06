from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.billing.catalog import get_plan_name, plan_key_from_plan_name
from app.core.entitlements import ALLOWED_FEATURES
from app.crud.plans import get_plan_by_name
from app.crud.subscriptions import get_active_subscription_for_tenant
from app.crud.tenant_settings import get_settings
from app.models.feature_entitlements import FeatureEntitlement
from app.models.plans import Plan
from app.models.tenant_settings import TenantSettings
from app.models.tenant_retention_policies import TenantRetentionPolicy
from app.core.retention import DATASET_RETENTION_LIMIT_KEYS


ENTITLEMENT_CACHE_TTL_SECONDS = 180
_ENTITLEMENT_CACHE: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}


def _cache_key(db: Session, tenant_id: int) -> tuple[int, str]:
    bind = db.get_bind()
    url = ""
    if bind is not None:
        try:
            url = str(bind.url)
        except Exception:
            url = ""
    return tenant_id, url


def _get_cached_entitlements(db: Session, tenant_id: int) -> dict[str, Any] | None:
    key = _cache_key(db, tenant_id)
    cached = _ENTITLEMENT_CACHE.get(key)
    if not cached:
        return None
    expires_at, payload = cached
    if time.monotonic() > expires_at:
        _ENTITLEMENT_CACHE.pop(key, None)
        return None
    return payload


def _set_cached_entitlements(db: Session, tenant_id: int, payload: dict[str, Any]) -> None:
    _ENTITLEMENT_CACHE[_cache_key(db, tenant_id)] = (
        time.monotonic() + ENTITLEMENT_CACHE_TTL_SECONDS,
        payload,
    )


def invalidate_entitlement_cache(tenant_id: int) -> None:
    keys = [key for key in _ENTITLEMENT_CACHE if key[0] == tenant_id]
    for key in keys:
        _ENTITLEMENT_CACHE.pop(key, None)


def _resolve_plan_context(
    db: Session,
    tenant_id: int,
) -> tuple[Plan | None, str | None, str | None]:
    subscription = get_active_subscription_for_tenant(db, tenant_id)
    plan = None
    plan_key = None
    if subscription:
        plan_key = subscription.plan_key
        if subscription.plan is not None:
            plan = subscription.plan
        elif subscription.plan_id:
            plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
    if plan is None and plan_key:
        plan_name = get_plan_name(plan_key)
        if plan_name:
            plan = get_plan_by_name(db, plan_name)
    if plan is None:
        plan = get_plan_by_name(db, "Free")
    plan_name = plan.name if plan else None
    if not plan_key and plan_name:
        plan_key = plan_key_from_plan_name(plan_name)
    return plan, plan_key, plan_name


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _apply_settings_overrides(
    limits: dict[str, Any],
    settings_row: TenantSettings | None,
) -> dict[str, Any]:
    effective = dict(limits)
    if settings_row is None:
        return effective
    override_map = {
        "retention_days": settings_row.retention_days,
        "event_retention_days": settings_row.event_retention_days,
        "raw_ip_retention_days": settings_row.ip_raw_retention_days,
    }
    for key, setting_value in override_map.items():
        desired = _coerce_positive_int(setting_value)
        if desired is None:
            continue
        limit_value = _coerce_positive_int(effective.get(key))
        if limit_value is None:
            effective[key] = desired
        else:
            effective[key] = min(desired, limit_value)
    return effective


def _apply_override_payload(
    payload: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    if not overrides:
        return payload
    features = dict(payload.get("features", {}))
    limits = dict(payload.get("limits", {}))
    for feature, enabled in (overrides.get("features") or {}).items():
        if feature in ALLOWED_FEATURES:
            features[feature] = bool(enabled)
    for key, value in (overrides.get("limits") or {}).items():
        if value is not None:
            limits[key] = value
    payload["features"] = features
    payload["limits"] = limits
    return payload


def _apply_dataset_retention_policies(
    limits: dict[str, Any],
    *,
    policies: list[TenantRetentionPolicy] | None = None,
) -> dict[str, Any]:
    if not policies:
        return limits
    effective = dict(limits)
    dataset_limits: dict[str, int] = dict(effective.get("dataset_retention_days") or {})

    def _resolve_limit_value(limit_key) -> int | None:
        if not limit_key:
            return None
        keys = limit_key if isinstance(limit_key, (list, tuple)) else (limit_key,)
        for key in keys:
            value = _coerce_positive_int(effective.get(key))
            if value is not None:
                return value
        return None

    for policy in policies:
        desired = _coerce_positive_int(policy.retention_days)
        if desired is None:
            continue
        limit_key = DATASET_RETENTION_LIMIT_KEYS.get(policy.dataset_key)
        max_allowed = _resolve_limit_value(limit_key)
        if max_allowed is None:
            dataset_limits[policy.dataset_key] = desired
        else:
            dataset_limits[policy.dataset_key] = min(desired, max_allowed)
    if dataset_limits:
        effective["dataset_retention_days"] = dataset_limits
        if "audit_logs" in dataset_limits:
            effective["event_retention_days"] = dataset_limits["audit_logs"]
    return effective


def resolve_entitlements_for_tenant(
    db: Session,
    tenant_id: int,
    *,
    use_cache: bool = True,
    tenant_settings: TenantSettings | None = None,
    override_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if use_cache:
        cached = _get_cached_entitlements(db, tenant_id)
        if cached is not None:
            return cached

    plan, plan_key, plan_name = _resolve_plan_context(db, tenant_id)
    limits = dict(plan.limits_json or {}) if plan else {}
    features = {feature: False for feature in ALLOWED_FEATURES}
    if plan:
        for feature, enabled in (plan.features_json or {}).items():
            if feature in ALLOWED_FEATURES:
                features[feature] = bool(enabled)

    overrides = (
        db.query(FeatureEntitlement)
        .filter(FeatureEntitlement.tenant_id == tenant_id)
        .order_by(FeatureEntitlement.feature)
        .all()
    )
    for entitlement in overrides:
        if entitlement.feature in ALLOWED_FEATURES:
            features[entitlement.feature] = bool(entitlement.enabled)

    if tenant_settings is None:
        try:
            tenant_settings = get_settings(db, tenant_id)
        except Exception:
            tenant_settings = None
    limits = _apply_settings_overrides(limits, tenant_settings)
    policies = (
        db.query(TenantRetentionPolicy)
        .filter(TenantRetentionPolicy.tenant_id == tenant_id)
        .order_by(TenantRetentionPolicy.dataset_key)
        .all()
    )
    limits = _apply_dataset_retention_policies(limits, policies=policies)

    payload = {
        "features": features,
        "limits": limits,
        "plan_key": plan_key,
        "plan_name": plan_name,
    }
    payload = _apply_override_payload(payload, override_payload)
    if use_cache:
        _set_cached_entitlements(db, tenant_id, payload)
    return payload
