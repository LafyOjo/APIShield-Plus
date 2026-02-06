from __future__ import annotations

import random
from typing import Any, Iterable

from app.models.tenant_settings import TenantSettings


HIGH_PRIORITY_EVENT_TYPES = {
    "form_submit",
    "error",
}

HIGH_PRIORITY_PATH_PREFIXES = (
    "/checkout",
    "/login",
    "/signin",
)


def is_high_priority_event(event_type: str, path: str | None) -> bool:
    if event_type in HIGH_PRIORITY_EVENT_TYPES:
        return True
    if not path:
        return False
    path_value = str(path)
    return any(path_value.startswith(prefix) for prefix in HIGH_PRIORITY_PATH_PREFIXES)


def _coerce_rate(value: Any, default: float) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return default
    if rate < 0.0:
        return 0.0
    if rate > 1.0:
        return 1.0
    return rate


def _match_rule(rule: dict[str, Any], event_type: str, path: str | None) -> bool:
    rule_type = (rule.get("event_type") or "").strip().lower()
    if rule_type and rule_type != event_type:
        return False
    path_prefix = rule.get("path_prefix")
    if path_prefix:
        if not path or not str(path).startswith(str(path_prefix)):
            return False
    path_contains = rule.get("path_contains")
    if path_contains:
        if not path or str(path_contains) not in str(path):
            return False
    return True


def _select_rate(
    rules: Iterable[dict[str, Any]],
    *,
    event_type: str,
    path: str | None,
    default_rate: float,
) -> float:
    best_rate = default_rate
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not _match_rule(rule, event_type, path):
            continue
        best_rate = max(best_rate, _coerce_rate(rule.get("sample_rate"), default_rate))
    return best_rate


def resolve_sampling_config(
    settings_row: TenantSettings | None,
    *,
    default_rate: float,
) -> tuple[float, list[dict[str, Any]]]:
    config = {}
    if settings_row and isinstance(settings_row.alert_prefs, dict):
        config = settings_row.alert_prefs.get("sampling") or {}
    rules = config.get("rules") if isinstance(config, dict) else None
    if not isinstance(rules, list):
        rules = []
    rate = _coerce_rate(config.get("default_rate"), default_rate) if isinstance(config, dict) else default_rate
    return rate, [rule for rule in rules if isinstance(rule, dict)]


def should_keep_event(
    *,
    event_type: str,
    path: str | None,
    rules: list[dict[str, Any]],
    default_rate: float,
) -> bool:
    if is_high_priority_event(event_type, path):
        return True
    rate = _select_rate(rules, event_type=event_type, path=path, default_rate=default_rate)
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() <= rate
