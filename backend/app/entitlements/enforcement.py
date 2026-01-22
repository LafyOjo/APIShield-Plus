from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.usage import get_or_create_current_period_usage


def _coerce_positive_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def suggest_upgrade_plan(plan_key: str | None) -> str | None:
    if not plan_key:
        return None
    ladder = {
        "free": "pro",
        "starter": "pro",
        "pro": "business",
        "business": "enterprise",
    }
    return ladder.get(plan_key)


@dataclass
class PlanEnforcementError(Exception):
    code: str
    message: str
    status_code: int
    upgrade_plan_key: str | None = None
    limit: int | None = None
    current_usage: int | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.upgrade_plan_key:
            payload["upgrade_plan_key"] = self.upgrade_plan_key
        if self.limit is not None:
            payload["limit"] = self.limit
        if self.current_usage is not None:
            payload["current_usage"] = self.current_usage
        return payload


class PlanLimitExceeded(PlanEnforcementError):
    def __init__(
        self,
        message: str,
        *,
        limit: int | None,
        current_usage: int | None,
        upgrade_plan_key: str | None = None,
    ):
        super().__init__(
            code="plan_limit_exceeded",
            message=message,
            status_code=402,
            upgrade_plan_key=upgrade_plan_key,
            limit=limit,
            current_usage=current_usage,
        )


class FeatureNotEnabled(PlanEnforcementError):
    def __init__(
        self,
        message: str,
        *,
        upgrade_plan_key: str | None = None,
    ):
        super().__init__(
            code="feature_not_enabled",
            message=message,
            status_code=403,
            upgrade_plan_key=upgrade_plan_key,
        )


class RangeClampedNotice(PlanEnforcementError):
    def __init__(
        self,
        message: str,
        *,
        limit: int | None,
    ):
        super().__init__(
            code="range_clamped",
            message=message,
            status_code=200,
            limit=limit,
        )


@dataclass
class RangeClampResult:
    from_ts: datetime | None
    to_ts: datetime | None
    max_days: int | None
    clamped: bool
    notice: str | None = None


def read_current_usage(db, tenant_id: int) -> dict[str, int]:
    usage = get_or_create_current_period_usage(tenant_id, db=db)
    return {
        "events_ingested": int(usage.events_ingested or 0),
        "storage_bytes": int(usage.storage_bytes or 0),
    }


def require_feature(
    entitlements: dict[str, Any],
    feature: str,
    *,
    message: str | None = None,
    upgrade_plan_key: str | None = None,
) -> None:
    features = entitlements.get("features", {}) if entitlements else {}
    if features.get(feature):
        return
    plan_key = entitlements.get("plan_key") if entitlements else None
    upgrade_plan_key = upgrade_plan_key or suggest_upgrade_plan(plan_key)
    message = message or f"Feature '{feature}' is not enabled for this plan"
    raise FeatureNotEnabled(message, upgrade_plan_key=upgrade_plan_key)


def assert_limit(
    entitlements: dict[str, Any],
    limit_key: str,
    current_value: int | None,
    *,
    mode: str = "hard",
    message: str | None = None,
    upgrade_plan_key: str | None = None,
) -> bool:
    limits = entitlements.get("limits", {}) if entitlements else {}
    limit_value = _coerce_positive_int(limits.get(limit_key))
    if limit_value is None or current_value is None:
        return False
    if current_value < limit_value:
        return False
    plan_key = entitlements.get("plan_key") if entitlements else None
    upgrade_plan_key = upgrade_plan_key or suggest_upgrade_plan(plan_key)
    message = message or f"Plan limit reached for {limit_key}"
    if mode == "soft":
        return True
    raise PlanLimitExceeded(
        message,
        limit=limit_value,
        current_usage=current_value,
        upgrade_plan_key=upgrade_plan_key,
    )


def clamp_range(
    entitlements: dict[str, Any],
    limit_key: str,
    from_ts: datetime | None,
    to_ts: datetime | None,
    *,
    now: datetime | None = None,
) -> RangeClampResult:
    limits = entitlements.get("limits", {}) if entitlements else {}
    max_days = _coerce_positive_int(limits.get(limit_key))
    normalized_from = _normalize_ts(from_ts)
    normalized_to = _normalize_ts(to_ts)
    if max_days is None:
        return RangeClampResult(
            from_ts=normalized_from,
            to_ts=normalized_to,
            max_days=None,
            clamped=False,
        )
    now_ts = _normalize_ts(now) or datetime.utcnow()
    max_range_start = now_ts - timedelta(days=max_days)
    effective_to = normalized_to if normalized_to and normalized_to <= now_ts else now_ts
    effective_from = (
        normalized_from
        if normalized_from and normalized_from >= max_range_start
        else max_range_start
    )
    if effective_to < max_range_start:
        effective_to = now_ts
    clamped = effective_from != normalized_from or effective_to != normalized_to
    notice = None
    if clamped:
        notice = f"Time range limited to last {max_days} days for your plan."
    return RangeClampResult(
        from_ts=effective_from,
        to_ts=effective_to,
        max_days=max_days,
        clamped=clamped,
        notice=notice,
    )
