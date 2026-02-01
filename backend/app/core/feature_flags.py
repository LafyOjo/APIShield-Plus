from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.models.feature_flags import FeatureFlag


def _hash_bucket(key: str, *, modulo: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _normalize_rules(rules: dict | None) -> dict:
    if not isinstance(rules, dict):
        return {}
    return rules


def _tenant_in_list(values: list | None, *, tenant_id: int, tenant_slug: str | None) -> bool:
    if not values:
        return False
    for value in values:
        if value is None:
            continue
        if isinstance(value, int) and tenant_id == value:
            return True
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw.isdigit() and tenant_id == int(raw):
                return True
            if tenant_slug and raw == tenant_slug.strip().lower():
                return True
    return False


def _value_in_list(values: list | None, candidate: str | None) -> bool:
    if not values:
        return False
    if not candidate:
        return False
    candidate_norm = candidate.strip().lower()
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() == candidate_norm:
            return True
    return False


def evaluate_flag(
    flag: FeatureFlag,
    *,
    tenant_id: int,
    tenant_slug: str | None,
    user_id: int | None,
    role: str | None,
    plan_key: str | None,
) -> tuple[bool, str]:
    rules = _normalize_rules(flag.rules_json)
    allow_tenants = rules.get("allow_tenants") or []
    deny_tenants = rules.get("deny_tenants") or []
    allow_roles = rules.get("allow_roles") or []
    allow_plans = rules.get("allow_plans") or []

    if _tenant_in_list(deny_tenants, tenant_id=tenant_id, tenant_slug=tenant_slug):
        return False, "deny_list"

    if _tenant_in_list(allow_tenants, tenant_id=tenant_id, tenant_slug=tenant_slug):
        return True, "allow_list"

    if not flag.is_enabled_global:
        return False, "disabled_global"

    if allow_roles:
        if not _value_in_list(allow_roles, role):
            return False, "role_not_allowed"

    if allow_plans:
        if not _value_in_list(allow_plans, plan_key):
            return False, "plan_not_allowed"

    percent = rules.get("percent_rollout", 100)
    try:
        percent_value = int(percent)
    except (TypeError, ValueError):
        percent_value = 100

    if percent_value <= 0:
        return False, "percent_zero"
    if percent_value >= 100:
        return True, "percent_all"

    bucket_key = f"{flag.key}:{tenant_id}:{user_id or ''}"
    bucket = _hash_bucket(bucket_key, modulo=100)
    enabled = bucket < percent_value
    return enabled, "percent_rollout"


def is_enabled(
    db: Session,
    *,
    key: str,
    tenant_id: int,
    tenant_slug: str | None,
    user_id: int | None,
    role: str | None,
    plan_key: str | None,
) -> tuple[bool, str]:
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        return False, "missing"
    return evaluate_flag(
        flag,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        user_id=user_id,
        role=role,
        plan_key=plan_key,
    )
