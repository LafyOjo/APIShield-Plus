from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _get_value(item, key: str):
    if hasattr(item, key):
        return getattr(item, key)
    if isinstance(item, dict):
        return item.get(key)
    return None


def compute_baseline(
    metrics: Iterable[object],
    *,
    window_days: int = 14,
    now: datetime | None = None,
) -> float:
    now = _normalize_ts(now or datetime.utcnow())
    window_start = now - timedelta(days=window_days)
    total_sessions = 0
    total_conversions = 0
    fallback_rates: list[float] = []

    for metric in metrics:
        window_end = _normalize_ts(
            _get_value(metric, "window_end") or _get_value(metric, "captured_at")
        )
        if window_end and window_end < window_start:
            continue
        sessions = _get_value(metric, "sessions") or 0
        conversions = _get_value(metric, "conversions") or 0
        conversion_rate = _get_value(metric, "conversion_rate")
        if sessions:
            total_sessions += int(sessions)
            total_conversions += int(conversions)
        elif conversion_rate is not None:
            fallback_rates.append(float(conversion_rate))

    if total_sessions > 0:
        baseline = total_conversions / total_sessions
    elif fallback_rates:
        baseline = sum(fallback_rates) / len(fallback_rates)
    else:
        baseline = 0.0

    return max(0.0, min(1.0, baseline))


def compute_impact(
    *,
    observed_rate: float,
    baseline_rate: float,
    sessions: int,
    revenue_per_conversion: float | None = None,
) -> dict[str, float | None]:
    observed = max(0.0, min(1.0, float(observed_rate)))
    baseline = max(0.0, min(1.0, float(baseline_rate)))
    delta_rate = max(0.0, baseline - observed)
    safe_sessions = max(0, int(sessions or 0))
    lost_conversions = delta_rate * safe_sessions
    lost_revenue = None
    if revenue_per_conversion is not None:
        lost_revenue = lost_conversions * max(0.0, float(revenue_per_conversion))
    return {
        "observed_rate": observed,
        "baseline_rate": baseline,
        "delta_rate": delta_rate,
        "estimated_lost_conversions": lost_conversions,
        "estimated_lost_revenue": lost_revenue,
    }
