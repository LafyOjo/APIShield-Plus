from __future__ import annotations

from datetime import datetime, time, timezone
from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.entitlements import resolve_effective_entitlements
from app.core.tracing import trace_span
from app.models.incidents import Incident
from app.models.notification_deliveries import NotificationDelivery
from app.models.notification_rules import NotificationRule, NotificationRuleChannel
from app.models.revenue_impact import ImpactEstimate
from app.security.taxonomy import SeverityEnum


SEVERITY_RANK = {
    SeverityEnum.LOW.value: 1,
    SeverityEnum.MEDIUM.value: 2,
    SeverityEnum.HIGH.value: 3,
    SeverityEnum.CRITICAL.value: 4,
}

DEFAULT_COOLDOWN_SECONDS = 900


def _normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.utcnow()
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _bucket_start(value: datetime, cooldown_seconds: int) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    timestamp = int(value.timestamp())
    bucket = timestamp - (timestamp % cooldown_seconds)
    return datetime.fromtimestamp(bucket, tz=timezone.utc).replace(tzinfo=None)


def _parse_time(value: str) -> time | None:
    if not value or not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59:
        return None
    return time(hours, minutes, seconds)


def _is_quiet_hours(quiet_hours: dict[str, Any] | None, when: datetime) -> bool:
    if not quiet_hours or not isinstance(quiet_hours, dict):
        return False
    ranges = quiet_hours.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        return False
    tz_name = quiet_hours.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    local_time = when.replace(tzinfo=timezone.utc).astimezone(tz).time()
    for entry in ranges:
        if not isinstance(entry, dict):
            continue
        start = _parse_time(entry.get("start"))
        end = _parse_time(entry.get("end"))
        if start is None or end is None:
            continue
        if start <= end:
            if start <= local_time < end:
                return True
        else:
            if local_time >= start or local_time < end:
                return True
    return False


def _severity_allows(threshold: str | None, value: str | None) -> bool:
    if not threshold:
        return True
    if not value:
        return False
    return SEVERITY_RANK.get(value, 0) >= SEVERITY_RANK.get(threshold, 0)


def _match_paths(matchers: list[str], context: dict[str, Any]) -> bool:
    if not matchers:
        return True
    paths = []
    direct = context.get("request_path")
    if isinstance(direct, str):
        paths.append(direct)
    list_paths = context.get("paths")
    if isinstance(list_paths, list):
        paths.extend([item for item in list_paths if isinstance(item, str)])
    if not paths:
        return False
    for pattern in matchers:
        if not isinstance(pattern, str):
            continue
        for path in paths:
            if fnmatch(path, pattern):
                return True
    return False


def _match_filters(filters: dict[str, Any], context: dict[str, Any]) -> bool:
    if not filters:
        return True
    context_website_id = context.get("website_id", context.get("site_id"))
    context_env_id = context.get("environment_id", context.get("env_id"))
    if "website_id" in filters and filters.get("website_id") is not None:
        if context_website_id != filters.get("website_id"):
            return False
    if "env_id" in filters and filters.get("env_id") is not None:
        if context_env_id != filters.get("env_id"):
            return False
    categories = filters.get("categories")
    if isinstance(categories, list) and categories:
        if context.get("category") not in categories:
            return False
    severity_min = filters.get("severity_min") or filters.get("severity")
    if not _severity_allows(severity_min, context.get("severity")):
        return False
    matchers = filters.get("path_matchers")
    if isinstance(matchers, list) and not _match_paths(matchers, context):
        return False
    return True


def _match_thresholds(thresholds: dict[str, Any], context: dict[str, Any]) -> bool:
    if not thresholds:
        return True
    if "count_per_minute" in thresholds:
        count = context.get("count_per_minute")
        if count is None or count < thresholds.get("count_per_minute"):
            return False
    if "delta_percent" in thresholds:
        delta = context.get("delta_percent")
        if delta is None or delta < thresholds.get("delta_percent"):
            return False
    if "lost_revenue_min" in thresholds:
        lost = context.get("lost_revenue")
        if lost is None or lost < thresholds.get("lost_revenue_min"):
            return False
    if "confidence_min" in thresholds:
        confidence = context.get("confidence")
        if confidence is None or confidence < thresholds.get("confidence_min"):
            return False
    return True


def _extract_context(db: Session, context: Any) -> dict[str, Any]:
    if isinstance(context, Incident):
        impact = None
        if context.impact_estimate_id:
            impact = (
                db.query(ImpactEstimate)
                .filter(
                    ImpactEstimate.id == context.impact_estimate_id,
                    ImpactEstimate.tenant_id == context.tenant_id,
                )
                .first()
            )
        return {
            "type": "incident",
            "incident_id": context.id,
            "title": context.title,
            "category": context.category,
            "severity": context.severity,
            "website_id": context.website_id,
            "environment_id": context.environment_id,
            "first_seen_at": context.first_seen_at,
            "last_seen_at": context.last_seen_at,
            "primary_country_code": context.primary_country_code,
            "primary_ip_hash": context.primary_ip_hash,
            "impact": impact,
            "event_time": context.last_seen_at or context.first_seen_at,
        }
    if isinstance(context, ImpactEstimate):
        delta_percent = None
        if context.baseline_rate:
            delta_percent = abs(context.delta_rate) / context.baseline_rate * 100.0
        return {
            "type": "impact",
            "impact_estimate_id": context.id,
            "metric_key": context.metric_key,
            "website_id": context.website_id,
            "environment_id": context.environment_id,
            "baseline_rate": context.baseline_rate,
            "observed_rate": context.observed_rate,
            "delta_percent": delta_percent,
            "lost_revenue": context.estimated_lost_revenue,
            "confidence": context.confidence,
            "event_time": context.window_end,
        }
    if isinstance(context, dict):
        return dict(context)
    raise ValueError("Unsupported context payload for notifications")


def _build_map_link(context: dict[str, Any]) -> str | None:
    from_ts = context.get("first_seen_at") or context.get("from")
    to_ts = context.get("last_seen_at") or context.get("to")
    if not isinstance(from_ts, datetime) or not isinstance(to_ts, datetime):
        return None
    params = {
        "from": _normalize_timestamp(from_ts).isoformat(),
        "to": _normalize_timestamp(to_ts).isoformat(),
    }
    if context.get("website_id") is not None:
        params["website_id"] = str(context.get("website_id"))
    env_id = context.get("environment_id", context.get("env_id"))
    if env_id is not None:
        params["env_id"] = str(env_id)
    if context.get("category"):
        params["category"] = str(context.get("category"))
    if context.get("severity"):
        params["severity"] = str(context.get("severity"))
    if context.get("primary_ip_hash"):
        params["ip_hash"] = str(context.get("primary_ip_hash"))
    if context.get("primary_country_code"):
        params["country_code"] = str(context.get("primary_country_code"))
    return f"/dashboard/security/map?{urlencode(params)}"


def _build_events_link(context: dict[str, Any]) -> str | None:
    from_ts = context.get("from")
    to_ts = context.get("to")
    if not isinstance(from_ts, datetime) or not isinstance(to_ts, datetime):
        return None
    params = {
        "from": _normalize_timestamp(from_ts).isoformat(),
        "to": _normalize_timestamp(to_ts).isoformat(),
    }
    if context.get("website_id") is not None:
        params["website_id"] = str(context.get("website_id"))
    env_id = context.get("environment_id", context.get("env_id"))
    if env_id is not None:
        params["env_id"] = str(env_id)
    if context.get("category"):
        params["category"] = str(context.get("category"))
    if context.get("severity"):
        params["severity"] = str(context.get("severity"))
    return f"/dashboard/security/events?{urlencode(params)}"


def _build_payload(context: dict[str, Any], entitlements: dict[str, Any]) -> dict[str, Any]:
    payload_type = context.get("type")
    links: dict[str, Any] = {}
    map_link = _build_map_link(context)
    if map_link:
        links["map"] = map_link
    if context.get("incident_id"):
        links["incident"] = f"/dashboard/revenue-integrity/incidents/{context['incident_id']}"
    events_link = _build_events_link(context)
    if events_link:
        links["events"] = events_link

    if payload_type == "incident":
        impact = context.get("impact")
        impact_payload = None
        if impact:
            impact_payload = {
                "estimated_lost_revenue": impact.estimated_lost_revenue,
                "estimated_lost_conversions": impact.estimated_lost_conversions,
                "confidence": impact.confidence,
            }
        return {
            "type": "incident",
            "incident_id": context.get("incident_id"),
            "title": context.get("title"),
            "category": context.get("category"),
            "severity": context.get("severity"),
            "impact": impact_payload,
            "links": links or None,
        }

    if payload_type == "impact":
        return {
            "type": "conversion_drop",
            "impact_estimate_id": context.get("impact_estimate_id"),
            "metric_key": context.get("metric_key"),
            "baseline_rate": context.get("baseline_rate"),
            "observed_rate": context.get("observed_rate"),
            "delta_percent": context.get("delta_percent"),
            "estimated_lost_revenue": context.get("lost_revenue"),
            "confidence": context.get("confidence"),
            "links": links or None,
        }

    features = entitlements.get("features", {}) if entitlements else {}
    limits = entitlements.get("limits", {}) if entitlements else {}
    geo_enabled = bool(features.get("geo_map"))
    granularity = str(limits.get("geo_granularity") or "").lower()
    allow_asn = granularity == "asn" and geo_enabled

    top_countries = context.get("top_countries")
    top_asns = context.get("top_asns")
    if not geo_enabled:
        top_countries = None
        top_asns = None
    elif not allow_asn:
        top_asns = None

    return {
        "type": context.get("type") or "security_spike",
        "category": context.get("category"),
        "severity": context.get("severity"),
        "count_per_minute": context.get("count_per_minute"),
        "event_types": context.get("event_types"),
        "top_paths": context.get("paths") or context.get("top_paths"),
        "top_countries": top_countries,
        "top_asns": top_asns,
        "links": links or None,
    }


def _build_dedupe_key(
    *,
    rule_id: int,
    channel_id: int,
    context: dict[str, Any],
    bucket_start: datetime,
) -> str:
    context_key = None
    if context.get("incident_id"):
        context_key = f"incident:{context['incident_id']}"
    elif context.get("impact_estimate_id"):
        context_key = f"impact:{context['impact_estimate_id']}"
    else:
        website_id = context.get("website_id", context.get("site_id"))
        context_key = f"site:{website_id}:cat:{context.get('category')}"
    return f"{rule_id}:{channel_id}:{context_key}:{bucket_start.isoformat()}"


def _dispatch_impl(
    db: Session,
    *,
    event_type: str,
    tenant_id: int,
    context_obj: Any,
) -> list[NotificationDelivery]:
    rules = (
        db.query(NotificationRule)
        .filter(
            NotificationRule.tenant_id == tenant_id,
            NotificationRule.is_enabled.is_(True),
            NotificationRule.trigger_type == event_type,
        )
        .all()
    )
    if not rules:
        return []

    context = _extract_context(db, context_obj)
    entitlements = resolve_effective_entitlements(db, tenant_id)
    deliveries: list[NotificationDelivery] = []
    seen_dedupe: set[str] = set()

    for rule in rules:
        filters = rule.filters_json if isinstance(rule.filters_json, dict) else {}
        thresholds = rule.thresholds_json if isinstance(rule.thresholds_json, dict) else {}
        if not _match_filters(filters, context):
            continue
        if not _match_thresholds(thresholds, context):
            continue

        channel_ids = [
            row.channel_id
            for row in db.query(NotificationRuleChannel.channel_id)
            .filter(NotificationRuleChannel.rule_id == rule.id)
            .all()
        ]
        if not channel_ids:
            continue

        cooldown_seconds = thresholds.get("cooldown_seconds") or DEFAULT_COOLDOWN_SECONDS
        try:
            cooldown_seconds = int(cooldown_seconds)
        except (TypeError, ValueError):
            cooldown_seconds = DEFAULT_COOLDOWN_SECONDS

        event_time = _normalize_timestamp(context.get("event_time"))
        bucket_start = _bucket_start(event_time, cooldown_seconds)

        for channel_id in channel_ids:
            dedupe_key = _build_dedupe_key(
                rule_id=rule.id,
                channel_id=channel_id,
                context=context,
                bucket_start=bucket_start,
            )
            if dedupe_key in seen_dedupe:
                continue
            seen_dedupe.add(dedupe_key)
            exists = (
                db.query(NotificationDelivery.id)
                .filter(
                    NotificationDelivery.tenant_id == tenant_id,
                    NotificationDelivery.dedupe_key == dedupe_key,
                )
                .first()
            )
            if exists:
                continue

            payload = _build_payload(context, entitlements)
            status = "queued"
            error_message = None
            if _is_quiet_hours(rule.quiet_hours_json, event_time):
                status = "skipped"
                error_message = "quiet_hours"

            delivery = NotificationDelivery(
                tenant_id=tenant_id,
                rule_id=rule.id,
                channel_id=channel_id,
                status=status,
                dedupe_key=dedupe_key,
                payload_json=payload,
                error_message=error_message,
                attempt_count=0,
            )
            db.add(delivery)
            deliveries.append(delivery)

    if deliveries:
        db.commit()
        for delivery in deliveries:
            db.refresh(delivery)
    return deliveries


def dispatch(
    db: Session,
    *,
    event_type: str,
    tenant_id: int,
    context_obj: Any,
) -> list[NotificationDelivery]:
    with trace_span(
        "notification.dispatch",
        tenant_id=tenant_id,
        trigger_type=event_type,
    ):
        return _dispatch_impl(
            db,
            event_type=event_type,
            tenant_id=tenant_id,
            context_obj=context_obj,
        )
