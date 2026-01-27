from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.tenants import Tenant
from app.models.trust_scoring import TrustFactorAgg
from app.schemas.revenue_leaks import (
    RevenueLeakFactorSummary,
    RevenueLeakResponse,
    RevenueLeakSeriesPoint,
    RevenueLeakSummary,
)
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/revenue", tags=["revenue"])

SITE_PATH_SENTINEL = "__site__"


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_path(value: Optional[str]) -> tuple[Optional[str], bool]:
    if value is None:
        return None, False
    normalized = value.strip()
    if normalized == "":
        return None, False
    if normalized == SITE_PATH_SENTINEL:
        return None, True
    return normalized, True


def _resolve_tenant(db: Session, tenant_hint: str) -> Tenant:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    return _resolve_tenant(db, tenant_hint).id


@dataclass
class _LeakAggregate:
    path: Optional[str]
    website_id: int
    environment_id: int
    total_lost_revenue: float = 0.0
    lost_conversions: float = 0.0
    sessions: int = 0
    observed_conversions: int = 0
    baseline_weighted_sum: float = 0.0
    baseline_weight: int = 0
    confidence_sum: float = 0.0
    confidence_count: int = 0
    trust_score_first: Optional[int] = None
    trust_score_last: Optional[int] = None
    trust_score_first_bucket: Optional[datetime] = None
    trust_score_last_bucket: Optional[datetime] = None
    incident_ids: set[int] = field(default_factory=set)

    def add_row(self, row: RevenueLeakEstimate) -> None:
        if row.estimated_lost_revenue:
            self.total_lost_revenue += float(row.estimated_lost_revenue)
        if row.lost_conversions:
            self.lost_conversions += float(row.lost_conversions)
        self.sessions += int(row.sessions_in_bucket or 0)
        self.observed_conversions += int(row.observed_conversions or 0)
        if row.baseline_conversion_rate is not None and row.sessions_in_bucket:
            self.baseline_weighted_sum += float(row.baseline_conversion_rate) * int(
                row.sessions_in_bucket
            )
            self.baseline_weight += int(row.sessions_in_bucket)
        if row.confidence is not None:
            self.confidence_sum += float(row.confidence)
            self.confidence_count += 1
        if row.linked_trust_score is not None and row.bucket_start is not None:
            if self.trust_score_first_bucket is None or row.bucket_start < self.trust_score_first_bucket:
                self.trust_score_first_bucket = row.bucket_start
                self.trust_score_first = int(row.linked_trust_score)
            if self.trust_score_last_bucket is None or row.bucket_start > self.trust_score_last_bucket:
                self.trust_score_last_bucket = row.bucket_start
                self.trust_score_last = int(row.linked_trust_score)
        explanation = row.explanation_json if isinstance(row.explanation_json, dict) else {}
        incident_ids = explanation.get("incident_ids")
        if isinstance(incident_ids, list):
            for value in incident_ids:
                if isinstance(value, int):
                    self.incident_ids.add(value)


def _build_series(rows: list[RevenueLeakEstimate]) -> list[RevenueLeakSeriesPoint]:
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda row: row.bucket_start or datetime.min)
    series: list[RevenueLeakSeriesPoint] = []
    for row in rows_sorted:
        series.append(
            RevenueLeakSeriesPoint(
                bucket_start=row.bucket_start,
                estimated_lost_revenue=row.estimated_lost_revenue,
                trust_score=row.linked_trust_score,
                confidence=row.confidence,
            )
        )
    return series


@router.get("/leaks", response_model=RevenueLeakResponse)
def list_revenue_leaks(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    path: str | None = None,
    limit: int = Query(15, ge=1, le=100),
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    require_feature(entitlements, "revenue_leaks", message="Revenue leak estimates require a Pro plan")
    include_demo = bool(include_demo and tenant.is_demo_mode)
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    if to_ts is None:
        to_ts = datetime.utcnow()
    if from_ts is None:
        from_ts = to_ts - timedelta(hours=24)
    if from_ts > to_ts:
        from_ts, to_ts = to_ts, from_ts

    path_value, has_path_filter = _normalize_path(path)

    query = db.query(RevenueLeakEstimate).filter(RevenueLeakEstimate.tenant_id == tenant_id)
    if not include_demo:
        query = query.filter(RevenueLeakEstimate.is_demo.is_(False))
    if website_id:
        query = query.filter(RevenueLeakEstimate.website_id == website_id)
    if env_id:
        query = query.filter(RevenueLeakEstimate.environment_id == env_id)
    if has_path_filter:
        if path_value is None:
            query = query.filter(RevenueLeakEstimate.path.is_(None))
        else:
            query = query.filter(RevenueLeakEstimate.path == path_value)
    query = query.filter(
        RevenueLeakEstimate.bucket_start >= from_ts,
        RevenueLeakEstimate.bucket_start <= to_ts,
    )
    rows = query.all()
    if not rows:
        return RevenueLeakResponse(items=[], series=[])

    aggregates: dict[tuple[Optional[str], int, int], _LeakAggregate] = {}
    for row in rows:
        key = (row.path, row.website_id, row.environment_id)
        if key not in aggregates:
            aggregates[key] = _LeakAggregate(
                path=row.path,
                website_id=row.website_id,
                environment_id=row.environment_id,
            )
        aggregates[key].add_row(row)

    items: list[RevenueLeakSummary] = []
    for agg in aggregates.values():
        sessions = agg.sessions
        observed_rate = agg.observed_conversions / sessions if sessions else 0.0
        baseline_rate = (
            agg.baseline_weighted_sum / agg.baseline_weight
            if agg.baseline_weight
            else None
        )
        confidence = (
            agg.confidence_sum / agg.confidence_count
            if agg.confidence_count
            else None
        )
        trust_delta = (
            agg.trust_score_last - agg.trust_score_first
            if agg.trust_score_last is not None and agg.trust_score_first is not None
            else None
        )
        items.append(
            RevenueLeakSummary(
                path=agg.path,
                website_id=agg.website_id,
                environment_id=agg.environment_id,
                total_lost_revenue=agg.total_lost_revenue,
                lost_conversions=agg.lost_conversions,
                sessions=agg.sessions,
                observed_conversion_rate=observed_rate,
                baseline_conversion_rate=baseline_rate,
                trust_score_latest=agg.trust_score_last,
                trust_score_delta=trust_delta,
                confidence=confidence,
                incident_ids=sorted(agg.incident_ids),
            )
        )

    if not has_path_filter:
        items = sorted(items, key=lambda item: item.total_lost_revenue or 0.0, reverse=True)[:limit]

    selected_keys = {
        (item.path, item.website_id, item.environment_id)
        for item in items
    }
    factor_query = (
        db.query(TrustFactorAgg)
        .filter(
            TrustFactorAgg.tenant_id == tenant_id,
            TrustFactorAgg.bucket_start >= from_ts,
            TrustFactorAgg.bucket_start <= to_ts,
        )
    )
    if not include_demo:
        factor_query = factor_query.filter(TrustFactorAgg.is_demo.is_(False))
    factor_rows = factor_query.all()
    factors_by_key: dict[
        tuple[Optional[str], int, int], dict[tuple[str, str], RevenueLeakFactorSummary]
    ] = {}
    for row in factor_rows:
        key = (row.path, row.website_id, row.environment_id)
        if key not in selected_keys:
            continue
        factor_key = (row.factor_type, row.severity)
        factor_map = factors_by_key.setdefault(key, {})
        summary = factor_map.get(factor_key)
        if summary is None:
            summary = RevenueLeakFactorSummary(
                factor_type=row.factor_type,
                severity=row.severity,
                count=0,
                evidence=row.evidence_json if isinstance(row.evidence_json, dict) else None,
            )
            factor_map[factor_key] = summary
        summary.count += int(row.count or 0)

    for item in items:
        factor_map = factors_by_key.get((item.path, item.website_id, item.environment_id), {})
        sorted_factors = sorted(
            factor_map.values(),
            key=lambda entry: entry.count,
            reverse=True,
        )
        item.top_factors = sorted_factors[:5]

    series: list[RevenueLeakSeriesPoint] = []
    if has_path_filter:
        series = _build_series(rows)

    return RevenueLeakResponse(items=items, series=series)
