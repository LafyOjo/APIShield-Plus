from typing import Any

from sqlalchemy.orm import Session

from app.core.entitlements import resolve_effective_entitlements
from app.models.notification_channels import NotificationChannel
from app.models.notification_rules import NotificationRule, NotificationRuleChannel
from app.security.taxonomy import SecurityCategoryEnum, SeverityEnum


ALLOWED_TRIGGER_TYPES = {
    "incident_created",
    "incident_severity_at_least",
    "conversion_drop_over_threshold",
    "login_fail_spike",
    "threat_spike",
    "new_country_login",
    "integrity_signal_detected",
}

ADVANCED_TRIGGER_TYPES = {
    "conversion_drop_over_threshold",
}

REQUIRED_THRESHOLD_KEYS = {
    "login_fail_spike": ["count_per_minute"],
    "threat_spike": ["count_per_minute"],
    "integrity_signal_detected": ["count_per_minute"],
}

DEFAULT_COOLDOWN_SECONDS = 900


def _coerce_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError("filters_json must be a JSON object")
    normalized = dict(filters)
    if "categories" in normalized:
        categories = normalized.get("categories")
        if not isinstance(categories, list):
            raise ValueError("filters_json.categories must be a list")
        allowed = {item.value for item in SecurityCategoryEnum}
        cleaned = []
        for entry in categories:
            if not isinstance(entry, str):
                raise ValueError("filters_json.categories entries must be strings")
            value = entry.strip().lower()
            if value not in allowed:
                raise ValueError("filters_json.categories contains invalid value")
            cleaned.append(value)
        normalized["categories"] = cleaned
    severity_key = None
    if "severity_min" in normalized:
        severity_key = "severity_min"
    elif "severity" in normalized:
        severity_key = "severity"
    if severity_key:
        value = normalized.get(severity_key)
        if not isinstance(value, str):
            raise ValueError("filters_json.severity must be a string")
        severity = value.strip().lower()
        allowed = {item.value for item in SeverityEnum}
        if severity not in allowed:
            raise ValueError("filters_json.severity value is invalid")
        normalized[severity_key] = severity
    return normalized


def _normalize_thresholds(thresholds: dict[str, Any] | None) -> dict[str, Any]:
    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds_json must be a JSON object")
    normalized = dict(thresholds)
    cooldown = _coerce_positive_int(normalized.get("cooldown_seconds"))
    normalized["cooldown_seconds"] = cooldown or DEFAULT_COOLDOWN_SECONDS
    if "confidence_min" in normalized:
        try:
            confidence = float(normalized["confidence_min"])
        except (TypeError, ValueError):
            raise ValueError("thresholds_json.confidence_min must be numeric")
        if confidence < 0 or confidence > 1:
            raise ValueError("thresholds_json.confidence_min must be between 0 and 1")
        normalized["confidence_min"] = confidence
    if "delta_percent" in normalized:
        try:
            delta = float(normalized["delta_percent"])
        except (TypeError, ValueError):
            raise ValueError("thresholds_json.delta_percent must be numeric")
        if delta <= 0:
            raise ValueError("thresholds_json.delta_percent must be positive")
        normalized["delta_percent"] = delta
    if "lost_revenue_min" in normalized:
        try:
            lost_revenue = float(normalized["lost_revenue_min"])
        except (TypeError, ValueError):
            raise ValueError("thresholds_json.lost_revenue_min must be numeric")
        if lost_revenue <= 0:
            raise ValueError("thresholds_json.lost_revenue_min must be positive")
        normalized["lost_revenue_min"] = lost_revenue
    if "count_per_minute" in normalized:
        count = _coerce_positive_int(normalized.get("count_per_minute"))
        if not count:
            raise ValueError("thresholds_json.count_per_minute must be positive")
        normalized["count_per_minute"] = count
    return normalized


def _validate_trigger_thresholds(
    trigger_type: str,
    *,
    filters: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    if trigger_type == "incident_severity_at_least":
        if "severity_min" not in filters and "severity" not in filters:
            raise ValueError("filters_json.severity_min required for incident severity trigger")
    if trigger_type == "conversion_drop_over_threshold":
        if not thresholds.get("delta_percent") and not thresholds.get("lost_revenue_min"):
            raise ValueError("thresholds_json.delta_percent or lost_revenue_min required")
    required_keys = REQUIRED_THRESHOLD_KEYS.get(trigger_type)
    if required_keys:
        for key in required_keys:
            if thresholds.get(key) is None:
                raise ValueError(f"thresholds_json.{key} required for trigger")


def _validate_advanced_triggers(
    trigger_type: str,
    thresholds: dict[str, Any],
    entitlements: dict[str, Any],
) -> None:
    features = entitlements.get("features", {}) if entitlements else {}
    advanced_enabled = bool(features.get("advanced_alerting"))
    requires_advanced = trigger_type in ADVANCED_TRIGGER_TYPES or bool(
        thresholds.get("lost_revenue_min")
    )
    if requires_advanced and not advanced_enabled:
        raise ValueError("Advanced alerting is required for this trigger")


def _coerce_limit(entitlements: dict[str, Any]) -> int | None:
    limits = entitlements.get("limits", {}) if entitlements else {}
    limit_value = limits.get("notification_rules")
    return _coerce_positive_int(limit_value)


def _enforce_rule_limit(db: Session, tenant_id: int, entitlements: dict[str, Any]) -> None:
    limit_value = _coerce_limit(entitlements)
    if limit_value is None:
        return
    current = db.query(NotificationRule).filter(NotificationRule.tenant_id == tenant_id).count()
    if current >= limit_value:
        raise ValueError("Notification rule limit reached for plan")


def _validate_channel_ids(
    db: Session,
    tenant_id: int,
    channel_ids: list[int],
) -> list[int]:
    if not channel_ids:
        return []
    cleaned = []
    for channel_id in channel_ids:
        if not isinstance(channel_id, int) or channel_id <= 0:
            raise ValueError("channel IDs must be positive integers")
        cleaned.append(channel_id)
    rows = (
        db.query(NotificationChannel.id)
        .filter(
            NotificationChannel.tenant_id == tenant_id,
            NotificationChannel.id.in_(cleaned),
        )
        .all()
    )
    found = {row.id for row in rows}
    if len(found) != len(set(cleaned)):
        raise ValueError("One or more channels do not belong to tenant")
    return cleaned


def _set_rule_channels(
    db: Session,
    *,
    rule: NotificationRule,
    channel_ids: list[int],
) -> None:
    db.query(NotificationRuleChannel).filter(
        NotificationRuleChannel.rule_id == rule.id
    ).delete()
    if not channel_ids:
        return
    db.add_all(
        [
            NotificationRuleChannel(rule_id=rule.id, channel_id=channel_id)
            for channel_id in channel_ids
        ]
    )


def create_rule(
    db: Session,
    *,
    tenant_id: int,
    name: str,
    trigger_type: str,
    created_by_user_id: int | None = None,
    is_enabled: bool = True,
    filters_json: dict[str, Any] | None = None,
    thresholds_json: dict[str, Any] | None = None,
    quiet_hours_json: dict[str, Any] | None = None,
    route_to_channel_ids: list[int] | None = None,
) -> NotificationRule:
    trigger_value = (trigger_type or "").strip()
    if trigger_value not in ALLOWED_TRIGGER_TYPES:
        raise ValueError("Unsupported trigger type")
    entitlements = resolve_effective_entitlements(db, tenant_id)
    _enforce_rule_limit(db, tenant_id, entitlements)

    filters = _normalize_filters(filters_json)
    thresholds = _normalize_thresholds(thresholds_json)
    _validate_trigger_thresholds(trigger_value, filters=filters, thresholds=thresholds)
    _validate_advanced_triggers(trigger_value, thresholds, entitlements)

    channel_ids = _validate_channel_ids(db, tenant_id, route_to_channel_ids or [])

    rule = NotificationRule(
        tenant_id=tenant_id,
        name=name,
        trigger_type=trigger_value,
        is_enabled=is_enabled,
        filters_json=filters or None,
        thresholds_json=thresholds or None,
        quiet_hours_json=quiet_hours_json,
        created_by_user_id=created_by_user_id,
    )
    db.add(rule)
    db.flush()
    _set_rule_channels(db, rule=rule, channel_ids=channel_ids)
    db.commit()
    db.refresh(rule)
    return rule


def list_rules(db: Session, tenant_id: int) -> list[NotificationRule]:
    return (
        db.query(NotificationRule)
        .filter(NotificationRule.tenant_id == tenant_id)
        .order_by(NotificationRule.id.desc())
        .all()
    )


def get_rule(db: Session, tenant_id: int, rule_id: int) -> NotificationRule | None:
    return (
        db.query(NotificationRule)
        .filter(
            NotificationRule.tenant_id == tenant_id,
            NotificationRule.id == rule_id,
        )
        .first()
    )


def update_rule(
    db: Session,
    tenant_id: int,
    rule_id: int,
    *,
    name: str | None = None,
    trigger_type: str | None = None,
    is_enabled: bool | None = None,
    filters_json: dict[str, Any] | None = None,
    thresholds_json: dict[str, Any] | None = None,
    quiet_hours_json: dict[str, Any] | None = None,
    route_to_channel_ids: list[int] | None = None,
) -> NotificationRule | None:
    rule = get_rule(db, tenant_id, rule_id)
    if not rule:
        return None

    trigger_value = rule.trigger_type
    if trigger_type is not None:
        trigger_value = (trigger_type or "").strip()
        if trigger_value not in ALLOWED_TRIGGER_TYPES:
            raise ValueError("Unsupported trigger type")

    filters = _normalize_filters(filters_json) if filters_json is not None else rule.filters_json or {}
    thresholds = (
        _normalize_thresholds(thresholds_json)
        if thresholds_json is not None
        else rule.thresholds_json or {}
    )
    _validate_trigger_thresholds(trigger_value, filters=filters, thresholds=thresholds)

    entitlements = resolve_effective_entitlements(db, tenant_id)
    _validate_advanced_triggers(trigger_value, thresholds, entitlements)

    if name is not None:
        rule.name = name
    if trigger_type is not None:
        rule.trigger_type = trigger_value
    if is_enabled is not None:
        rule.is_enabled = is_enabled
    if filters_json is not None:
        rule.filters_json = filters or None
    if thresholds_json is not None:
        rule.thresholds_json = thresholds or None
    if quiet_hours_json is not None:
        rule.quiet_hours_json = quiet_hours_json

    if route_to_channel_ids is not None:
        channel_ids = _validate_channel_ids(db, tenant_id, route_to_channel_ids)
        _set_rule_channels(db, rule=rule, channel_ids=channel_ids)

    db.commit()
    db.refresh(rule)
    return rule

