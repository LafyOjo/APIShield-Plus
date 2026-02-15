from __future__ import annotations

from datetime import datetime, timedelta
import csv
import io
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, case
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import get_current_user
from app.core.cache import build_cache_key, cache_get, cache_set, db_scope_id
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.entitlements.enforcement import require_feature, clamp_range
from app.models.enums import RoleEnum, WebsiteStatusEnum
from app.models.incidents import Incident
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.trust_scoring import TrustSnapshot
from app.models.websites import Website
from app.models.website_stack_profiles import WebsiteStackProfile
from app.models.tenants import Tenant
from app.crud.resellers import get_managed_tenant, get_reseller_account
from app.tenancy.dependencies import get_current_membership, _resolve_tenant_id
from app.schemas.portfolio import (
    PortfolioExportResponse,
    PortfolioIncidentSummary,
    PortfolioLeakHotspot,
    PortfolioSummary,
    PortfolioSummaryResponse,
    PortfolioWebsiteRead,
)


router = APIRouter(prefix="/portfolio", tags=["portfolio"])

ROLE_RANK = {
    RoleEnum.VIEWER: 1,
    RoleEnum.BILLING_ADMIN: 1,
    RoleEnum.ANALYST: 2,
    RoleEnum.SECURITY_ADMIN: 2,
    RoleEnum.ADMIN: 3,
    RoleEnum.OWNER: 4,
}


def _score_verified(score: int | None, confidence: float | None) -> bool:
    if score is None or confidence is None:
        return False
    return score >= 80 and confidence >= 0.6


def _ensure_role(role: RoleEnum | None, minimum: RoleEnum) -> None:
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant membership not found")
    actual = ROLE_RANK.get(role, 0)
    required = ROLE_RANK.get(minimum, 0)
    if actual < required:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insufficient role for tenant operation")


def _resolve_target_tenant(
    request: Request,
    db: Session,
    current_user,
    tenant_id_param: int | None,
) -> tuple[int, RoleEnum | None, bool]:
    if getattr(current_user, "is_partner_user", False):
        partner_role = getattr(current_user, "partner_role", None)
        if partner_role not in {"admin", "reseller_admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reseller admin required")
        if tenant_id_param is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id is required")
        account = get_reseller_account(db, partner_id=getattr(current_user, "partner_id", None))
        if not account or not account.is_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reseller account not enabled")
        managed = get_managed_tenant(db, tenant_id=tenant_id_param)
        if not managed or managed.reseller_partner_id != current_user.partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Managed tenant not found")
        return managed.tenant_id, None, True

    tenant_id = _resolve_tenant_id(request)
    membership = get_current_membership(db, current_user, tenant_id)
    if tenant_id_param is not None and membership.tenant_id != tenant_id_param:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant membership not found")
    return membership.tenant_id, membership.role, False


def _latest_snapshot_subquery(db: Session, tenant_id: int):
    return (
        db.query(
            TrustSnapshot.website_id.label("website_id"),
            func.max(TrustSnapshot.bucket_start).label("bucket_start"),
        )
        .filter(
            TrustSnapshot.tenant_id == tenant_id,
            TrustSnapshot.path.is_(None),
            TrustSnapshot.is_demo.is_(False),
        )
        .group_by(TrustSnapshot.website_id)
        .subquery()
    )


def _open_incidents_subquery(db: Session, tenant_id: int):
    return (
        db.query(
            Incident.website_id.label("website_id"),
            func.count(Incident.id).label("open_total"),
            func.sum(
                case((Incident.severity == "critical", 1), else_=0)
            ).label("open_critical"),
            func.max(Incident.last_seen_at).label("last_incident_at"),
        )
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.is_demo.is_(False),
            Incident.status != "resolved",
        )
        .group_by(Incident.website_id)
        .subquery()
    )


def _revenue_leak_subquery(db: Session, tenant_id: int, *, from_ts: datetime):
    return (
        db.query(
            RevenueLeakEstimate.website_id.label("website_id"),
            func.sum(RevenueLeakEstimate.estimated_lost_revenue).label("lost_revenue"),
        )
        .filter(
            RevenueLeakEstimate.tenant_id == tenant_id,
            RevenueLeakEstimate.is_demo.is_(False),
            RevenueLeakEstimate.bucket_start >= from_ts,
        )
        .group_by(RevenueLeakEstimate.website_id)
        .subquery()
    )


def _fetch_portfolio_websites(
    db: Session,
    *,
    tenant_id: int,
    status_filter: str | None,
    stack_filter: str | None,
    region_filter: str | None,
    leak_window_days: int = 7,
) -> list[PortfolioWebsiteRead]:
    trust_subq = _latest_snapshot_subquery(db, tenant_id)
    trust_alias = aliased(TrustSnapshot)
    incidents_subq = _open_incidents_subquery(db, tenant_id)
    leak_from = datetime.utcnow() - timedelta(days=leak_window_days)
    leak_subq = _revenue_leak_subquery(db, tenant_id, from_ts=leak_from)

    query = (
        db.query(
            Website.id,
            Website.domain,
            Website.display_name,
            Website.status,
            Tenant.data_region,
            WebsiteStackProfile.stack_type,
            trust_alias.trust_score,
            trust_alias.confidence,
            trust_alias.bucket_start,
            incidents_subq.c.open_total,
            incidents_subq.c.open_critical,
            incidents_subq.c.last_incident_at,
            leak_subq.c.lost_revenue,
        )
        .join(Tenant, Tenant.id == Website.tenant_id)
        .outerjoin(
            WebsiteStackProfile,
            WebsiteStackProfile.website_id == Website.id,
        )
        .outerjoin(
            trust_subq,
            trust_subq.c.website_id == Website.id,
        )
        .outerjoin(
            trust_alias,
            (trust_alias.website_id == trust_subq.c.website_id)
            & (trust_alias.bucket_start == trust_subq.c.bucket_start),
        )
        .outerjoin(incidents_subq, incidents_subq.c.website_id == Website.id)
        .outerjoin(leak_subq, leak_subq.c.website_id == Website.id)
        .filter(
            Website.tenant_id == tenant_id,
            Website.deleted_at.is_(None),
            Website.status != WebsiteStatusEnum.DELETED,
        )
    )

    if status_filter:
        query = query.filter(Website.status == status_filter)
    if stack_filter:
        query = query.filter(WebsiteStackProfile.stack_type == stack_filter)
    if region_filter:
        query = query.filter(Tenant.data_region == region_filter)

    rows = query.order_by(Website.created_at.desc()).all()
    results: list[PortfolioWebsiteRead] = []
    for row in rows:
        trust_score = row.trust_score if row.trust_score is not None else None
        confidence = row.confidence if row.confidence is not None else None
        results.append(
            PortfolioWebsiteRead(
                website_id=row.id,
                domain=row.domain,
                display_name=row.display_name,
                status=row.status,
                stack_type=row.stack_type,
                data_region=row.data_region,
                trust_score_current=trust_score,
                trust_confidence=confidence,
                trust_verified=_score_verified(trust_score, confidence),
                trust_updated_at=row.bucket_start,
                incidents_open_total=int(row.open_total or 0),
                incidents_open_critical=int(row.open_critical or 0),
                revenue_leak_7d=float(row.lost_revenue or 0.0),
                last_incident_at=row.last_incident_at,
            )
        )
    return results


def _build_summary(
    db: Session,
    *,
    tenant_id: int,
    from_ts: datetime,
    to_ts: datetime,
    status_filter: str | None,
    stack_filter: str | None,
    region_filter: str | None,
    range_notice: str | None,
) -> PortfolioSummary:
    website_query = (
        db.query(Website.id)
        .join(Tenant, Tenant.id == Website.tenant_id)
        .outerjoin(WebsiteStackProfile, WebsiteStackProfile.website_id == Website.id)
        .filter(
            Website.tenant_id == tenant_id,
            Website.deleted_at.is_(None),
            Website.status != WebsiteStatusEnum.DELETED,
        )
    )
    if status_filter:
        website_query = website_query.filter(Website.status == status_filter)
    if stack_filter:
        website_query = website_query.filter(WebsiteStackProfile.stack_type == stack_filter)
    if region_filter:
        website_query = website_query.filter(Tenant.data_region == region_filter)
    website_ids = [row[0] for row in website_query.all()]

    if not website_ids:
        return PortfolioSummary(
            website_count=0,
            avg_trust_score=None,
            open_incidents_total=0,
            open_incidents_critical=0,
            total_revenue_leak=0.0,
            top_incidents=[],
            top_leak_paths=[],
            range_notice=range_notice,
        )

    trust_avg = (
        db.query(func.avg(TrustSnapshot.trust_score))
        .filter(
            TrustSnapshot.tenant_id == tenant_id,
            TrustSnapshot.website_id.in_(website_ids),
            TrustSnapshot.path.is_(None),
            TrustSnapshot.is_demo.is_(False),
            TrustSnapshot.bucket_start >= from_ts,
            TrustSnapshot.bucket_start <= to_ts,
        )
        .scalar()
    )

    incident_rows = (
        db.query(
            Incident.website_id,
            func.count(Incident.id).label("open_total"),
            func.sum(case((Incident.severity == "critical", 1), else_=0)).label("open_critical"),
        )
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.website_id.in_(website_ids),
            Incident.is_demo.is_(False),
            Incident.status != "resolved",
        )
        .group_by(Incident.website_id)
        .all()
    )
    open_total = sum(int(row.open_total or 0) for row in incident_rows)
    open_critical = sum(int(row.open_critical or 0) for row in incident_rows)

    leak_total = (
        db.query(func.sum(RevenueLeakEstimate.estimated_lost_revenue))
        .filter(
            RevenueLeakEstimate.tenant_id == tenant_id,
            RevenueLeakEstimate.website_id.in_(website_ids),
            RevenueLeakEstimate.is_demo.is_(False),
            RevenueLeakEstimate.bucket_start >= from_ts,
            RevenueLeakEstimate.bucket_start <= to_ts,
        )
        .scalar()
    )
    leak_total_value = float(leak_total or 0.0)

    top_incidents_rows = (
        db.query(Incident)
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.website_id.in_(website_ids),
            Incident.is_demo.is_(False),
            Incident.status != "resolved",
        )
        .order_by(Incident.last_seen_at.desc())
        .limit(6)
        .all()
    )
    top_incidents = [
        PortfolioIncidentSummary(
            incident_id=row.id,
            website_id=row.website_id,
            title=row.title,
            severity=row.severity,
            status=row.status,
            category=row.category,
            last_seen_at=row.last_seen_at,
        )
        for row in top_incidents_rows
    ]

    leak_rows = (
        db.query(
            RevenueLeakEstimate.website_id,
            RevenueLeakEstimate.path,
            func.sum(RevenueLeakEstimate.estimated_lost_revenue).label("lost_revenue"),
        )
        .filter(
            RevenueLeakEstimate.tenant_id == tenant_id,
            RevenueLeakEstimate.website_id.in_(website_ids),
            RevenueLeakEstimate.is_demo.is_(False),
            RevenueLeakEstimate.bucket_start >= from_ts,
            RevenueLeakEstimate.bucket_start <= to_ts,
        )
        .group_by(RevenueLeakEstimate.website_id, RevenueLeakEstimate.path)
        .order_by(func.sum(RevenueLeakEstimate.estimated_lost_revenue).desc())
        .limit(6)
        .all()
    )
    leak_hotspots = [
        PortfolioLeakHotspot(
            website_id=row.website_id,
            path=row.path,
            estimated_lost_revenue=float(row.lost_revenue or 0.0),
        )
        for row in leak_rows
        if row.lost_revenue is not None
    ]

    return PortfolioSummary(
        website_count=len(website_ids),
        avg_trust_score=float(trust_avg) if trust_avg is not None else None,
        open_incidents_total=open_total,
        open_incidents_critical=open_critical,
        total_revenue_leak=leak_total_value,
        top_incidents=top_incidents,
        top_leak_paths=leak_hotspots,
        range_notice=range_notice,
    )


def _build_export_csv(items: Iterable[PortfolioWebsiteRead]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "website_id",
            "domain",
            "display_name",
            "status",
            "stack_type",
            "data_region",
            "trust_score_current",
            "trust_confidence",
            "trust_verified",
            "trust_updated_at",
            "incidents_open_total",
            "incidents_open_critical",
            "revenue_leak_7d",
            "last_incident_at",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.website_id,
                item.domain,
                item.display_name or "",
                item.status,
                item.stack_type or "",
                item.data_region or "",
                item.trust_score_current if item.trust_score_current is not None else "",
                item.trust_confidence if item.trust_confidence is not None else "",
                "true" if item.trust_verified else "false",
                item.trust_updated_at.isoformat() if item.trust_updated_at else "",
                item.incidents_open_total,
                item.incidents_open_critical,
                f"{item.revenue_leak_7d:.2f}",
                item.last_incident_at.isoformat() if item.last_incident_at else "",
            ]
        )
    return output.getvalue()


@router.get("/websites", response_model=list[PortfolioWebsiteRead])
def list_portfolio_websites(
    request: Request,
    tenant_id: int | None = None,
    status: str | None = None,
    stack_type: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tenant_id_value, role, _partner_mode = _resolve_target_tenant(request, db, current_user, tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id_value)
    require_feature(entitlements, "portfolio_view", message="Portfolio scorecards require a Business plan")
    if role is not None:
        _ensure_role(role, RoleEnum.VIEWER)

    return _fetch_portfolio_websites(
        db,
        tenant_id=tenant_id_value,
        status_filter=status,
        stack_filter=stack_type,
        region_filter=region,
    )


@router.get("/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    request: Request,
    tenant_id: int | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    status: str | None = None,
    stack_type: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tenant_id_value, role, _partner_mode = _resolve_target_tenant(request, db, current_user, tenant_id)
    requested_from_ts = from_ts
    requested_to_ts = to_ts
    entitlements = resolve_effective_entitlements(db, tenant_id_value)
    require_feature(entitlements, "portfolio_view", message="Portfolio scorecards require a Business plan")
    if role is not None:
        _ensure_role(role, RoleEnum.VIEWER)

    clamp_result = clamp_range(entitlements, "retention_days", from_ts, to_ts)
    effective_from = clamp_result.from_ts or datetime.utcnow() - timedelta(days=7)
    effective_to = clamp_result.to_ts or datetime.utcnow()

    cache_key = build_cache_key(
        "portfolio.summary",
        tenant_id=tenant_id_value,
        db_scope=db_scope_id(db),
        filters={
            # Keep cache key stable for repeated requests with same user inputs.
            "from": requested_from_ts,
            "to": requested_to_ts,
            "status": status,
            "stack_type": stack_type,
            "region": region,
            "range_notice": clamp_result.notice,
            "plan_key": entitlements.get("plan_key"),
        },
    )
    cached = cache_get(cache_key, cache_name="portfolio.summary")
    if cached is not None:
        return PortfolioSummaryResponse(**cached)

    summary = _build_summary(
        db,
        tenant_id=tenant_id_value,
        from_ts=effective_from,
        to_ts=effective_to,
        status_filter=status,
        stack_filter=stack_type,
        region_filter=region,
        range_notice=clamp_result.notice,
    )
    payload = PortfolioSummaryResponse(summary=summary)
    cache_set(
        cache_key,
        payload,
        ttl=settings.CACHE_TTL_PORTFOLIO_SUMMARY,
        cache_name="portfolio.summary",
    )
    return payload


@router.get("/export", response_model=PortfolioExportResponse)
def export_portfolio(
    request: Request,
    tenant_id: int | None = None,
    status: str | None = None,
    stack_type: str | None = None,
    region: str | None = None,
    format: str = "json",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tenant_id_value, role, _partner_mode = _resolve_target_tenant(request, db, current_user, tenant_id)
    entitlements = resolve_effective_entitlements(db, tenant_id_value)
    require_feature(entitlements, "portfolio_exports", message="Portfolio exports require an Enterprise plan")
    if role is not None:
        _ensure_role(role, RoleEnum.ADMIN)

    items = _fetch_portfolio_websites(
        db,
        tenant_id=tenant_id_value,
        status_filter=status,
        stack_filter=stack_type,
        region_filter=region,
    )
    generated_at = datetime.utcnow()

    if format.lower() == "csv":
        csv_payload = _build_export_csv(items)
        filename = f"portfolio_{tenant_id_value}_{generated_at.strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=csv_payload,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
            },
        )
    if format.lower() != "json":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format")

    return PortfolioExportResponse(
        generated_at=generated_at,
        items=items,
    )
