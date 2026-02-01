from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.feature_flags import _normalize_rules, _tenant_in_list, _value_in_list
from app.core.time import utcnow
from app.crud.affiliates import get_partner_by_code
from app.models.feature_flags import Experiment, ExperimentAssignment


def _hash_value(key: str, *, modulo: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def _is_targeted(
    rules: dict,
    *,
    tenant_id: int,
    tenant_slug: str | None,
    role: str | None,
    plan_key: str | None,
) -> bool:
    allow_tenants = rules.get("allow_tenants") or []
    deny_tenants = rules.get("deny_tenants") or []
    allow_roles = rules.get("allow_roles") or []
    allow_plans = rules.get("allow_plans") or []

    if _tenant_in_list(deny_tenants, tenant_id=tenant_id, tenant_slug=tenant_slug):
        return False
    if allow_tenants and _tenant_in_list(allow_tenants, tenant_id=tenant_id, tenant_slug=tenant_slug):
        return True

    if allow_roles and not _value_in_list(allow_roles, role):
        return False
    if allow_plans and not _value_in_list(allow_plans, plan_key):
        return False

    percent = rules.get("percent_rollout", 100)
    try:
        percent_value = int(percent)
    except (TypeError, ValueError):
        percent_value = 100
    if percent_value <= 0:
        return False
    if percent_value >= 100:
        return True

    bucket = _hash_value(f"experiment:{tenant_id}", modulo=100)
    return bucket < percent_value


def _choose_variant(variants: list[dict], seed: int) -> str | None:
    total = 0
    weighted: list[tuple[str, int]] = []
    for entry in variants:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        try:
            weight = int(entry.get("weight", 0))
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            continue
        weighted.append((str(name), weight))
        total += weight
    if total <= 0:
        return None
    pick = seed % total
    cursor = 0
    for name, weight in weighted:
        cursor += weight
        if pick < cursor:
            return name
    return weighted[-1][0] if weighted else None


def assign_variant(
    db: Session,
    *,
    experiment_key: str,
    tenant_id: int,
    tenant_slug: str | None,
    user_id: int | None,
    role: str | None,
    plan_key: str | None,
) -> ExperimentAssignment | None:
    experiment = db.query(Experiment).filter(Experiment.key == experiment_key).first()
    if not experiment or not experiment.is_enabled:
        return None

    rules = _normalize_rules(experiment.targeting_rules_json)
    if not _is_targeted(rules, tenant_id=tenant_id, tenant_slug=tenant_slug, role=role, plan_key=plan_key):
        return None

    assignment = (
        db.query(ExperimentAssignment)
        .filter(
            ExperimentAssignment.experiment_key == experiment_key,
            ExperimentAssignment.tenant_id == tenant_id,
            ExperimentAssignment.user_id == user_id,
        )
        .first()
    )
    if assignment:
        return assignment

    variants = experiment.variants_json if isinstance(experiment.variants_json, list) else []
    seed_key = f"{experiment_key}:{tenant_id}:{user_id or 'tenant'}"
    seed = _hash_value(seed_key, modulo=100000)
    variant = _choose_variant(variants, seed)
    if not variant:
        return None

    assignment = ExperimentAssignment(
        experiment_key=experiment_key,
        tenant_id=tenant_id,
        user_id=user_id,
        variant=variant,
        assigned_at=utcnow(),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment
