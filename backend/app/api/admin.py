from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_platform_admin
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.core.security import create_access_token
from app.crud.audit import create_audit_log
from app.crud.subscriptions import get_active_subscription_for_tenant
from app.models.activation_metrics import ActivationMetric
from app.models.behaviour_events import BehaviourEvent
from app.models.data_exports import DataExportRun
from app.models.incidents import Incident
from app.models.memberships import Membership
from app.models.notification_deliveries import NotificationDelivery
from app.models.notification_rules import NotificationRule
from app.models.retention_runs import RetentionRun
from app.models.security_events import SecurityEvent
from app.models.tenants import Tenant
from app.models.tenant_usage import TenantUsage
from app.models.websites import Website
from app.jobs.activation_metrics import run_activation_metrics_job
from app.schemas.admin import (
    AdminHealthSummary,
    AdminIncidentSummary,
    AdminSubscriptionSummary,
    AdminSupportViewAsRequest,
    AdminSupportViewAsResponse,
    AdminTenantDetail,
    AdminTenantListItem,
    AdminUsageSummary,
)
from app.schemas.activation_metrics import (
    ActivationMetricRead,
    ActivationMetricsResponse,
    ActivationSummary,
)


router = APIRouter(prefix="/admin", tags=["admin"])


def _audit_admin_action(
    db: Session,
    *,
    tenant_id: int,
    username: str,
    event: str,
    request: Request | None = None,
) -> None:
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=username,
        event=event,
        request=request,
    )


def _build_tenant_list_item(tenant: Tenant) -> AdminTenantListItem:
    return AdminTenantListItem(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        data_region=tenant.data_region or "us",
        created_region=tenant.created_region or "us",
        created_at=tenant.created_at,
        deleted_at=tenant.deleted_at,
    )


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/tenants", response_model=list[AdminTenantListItem])
def list_tenants(
    request: Request,
    query: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    q = (query or "").strip()
    tenant_query = db.query(Tenant)
    if q:
        if q.isdigit():
            tenant_query = tenant_query.filter(Tenant.id == int(q))
        else:
            like = f"%{q}%"
            tenant_query = tenant_query.filter(
                (Tenant.name.ilike(like)) | (Tenant.slug.ilike(like))
            )
    tenants = tenant_query.order_by(Tenant.created_at.desc()).limit(limit).all()
    items = [_build_tenant_list_item(t) for t in tenants]
    # Audit each tenant returned (bounded by limit).
    for tenant in tenants:
        _audit_admin_action(
            db,
            tenant_id=tenant.id,
            username=current_user.username,
            event=f"admin.tenant_search:{q or 'all'}",
            request=request,
        )
    return items


@router.get("/tenants/{tenant_id}", response_model=AdminTenantDetail)
def get_tenant_detail(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    subscription = get_active_subscription_for_tenant(db, tenant_id)
    plan_name = subscription.plan.name if subscription and subscription.plan else None
    subscription_summary = AdminSubscriptionSummary(
        plan_name=plan_name,
        status=subscription.status if subscription else None,
        current_period_end=subscription.current_period_end if subscription else None,
    )

    entitlements = resolve_effective_entitlements(db, tenant_id)

    usage = (
        db.query(TenantUsage)
        .filter(TenantUsage.tenant_id == tenant_id)
        .order_by(TenantUsage.period_start.desc())
        .first()
    )
    websites_count = (
        db.query(Website)
        .filter(Website.tenant_id == tenant_id, Website.deleted_at.is_(None))
        .count()
    )
    members_count = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id)
        .count()
    )
    usage_summary = AdminUsageSummary(
        period_start=usage.period_start if usage else None,
        period_end=usage.period_end if usage else None,
        events_ingested=usage.events_ingested if usage else 0,
        storage_bytes=usage.storage_bytes if usage else 0,
        websites_count=websites_count,
        members_count=members_count,
    )

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)
    seven_days_ago = now - timedelta(days=7)

    last_ingest_at = (
        db.query(func.max(BehaviourEvent.ingested_at))
        .filter(BehaviourEvent.tenant_id == tenant_id)
        .scalar()
    )
    ingest_1h = (
        db.query(BehaviourEvent)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.ingested_at >= one_hour_ago,
        )
        .count()
    )
    ingest_24h = (
        db.query(BehaviourEvent)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.ingested_at >= one_day_ago,
        )
        .count()
    )
    ingest_rate_limit = (
        db.query(SecurityEvent)
        .filter(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.created_at >= one_hour_ago,
            SecurityEvent.event_type.in_(
                ["rate_limit", "ingest_rate_limit", "ingest_abuse", "ingest_rejected"]
            ),
        )
        .count()
    )
    security_1h = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.tenant_id == tenant_id, SecurityEvent.created_at >= one_hour_ago)
        .count()
    )
    rejected_1h = (
        db.query(SecurityEvent)
        .filter(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.created_at >= one_hour_ago,
            SecurityEvent.event_type.in_(["ingest_rejected", "ingest_blocked"]),
        )
        .count()
    )
    denom = ingest_1h + rejected_1h
    success_rate = float(ingest_1h) / denom if denom else None

    export_failures = (
        db.query(DataExportRun)
        .filter(
            DataExportRun.tenant_id == tenant_id,
            DataExportRun.status == "failed",
            DataExportRun.started_at >= seven_days_ago,
        )
        .count()
    )
    retention_failures = (
        db.query(RetentionRun)
        .filter(
            RetentionRun.tenant_id == tenant_id,
            RetentionRun.status == "failed",
            RetentionRun.started_at >= seven_days_ago,
        )
        .count()
    )
    notification_failures = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.tenant_id == tenant_id,
            NotificationDelivery.status == "failed",
            NotificationDelivery.created_at >= one_day_ago,
        )
        .count()
    )

    health = AdminHealthSummary(
        last_ingest_at=last_ingest_at,
        ingest_events_1h=ingest_1h,
        ingest_events_24h=ingest_24h,
        ingest_success_rate_1h=success_rate,
        ingest_rate_limit_1h=ingest_rate_limit,
        security_events_1h=security_1h,
        export_failures_7d=export_failures,
        retention_failures_7d=retention_failures,
        notification_failures_24h=notification_failures,
    )

    _audit_admin_action(
        db,
        tenant_id=tenant_id,
        username=current_user.username,
        event="admin.tenant_view",
        request=request,
    )

    return AdminTenantDetail(
        tenant=_build_tenant_list_item(tenant),
        subscription=subscription_summary,
        entitlements=entitlements,
        usage=usage_summary,
        health=health,
    )


@router.get("/tenants/{tenant_id}/incidents", response_model=list[AdminIncidentSummary])
def list_tenant_incidents(
    tenant_id: int,
    request: Request,
    status_value: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    query = db.query(Incident).filter(Incident.tenant_id == tenant_id)
    if status_value:
        query = query.filter(Incident.status == status_value)
    rows = query.order_by(Incident.last_seen_at.desc()).limit(limit).all()
    _audit_admin_action(
        db,
        tenant_id=tenant_id,
        username=current_user.username,
        event="admin.incident_list",
        request=request,
    )
    return [
        AdminIncidentSummary(
            id=row.id,
            status=row.status,
            severity=row.severity,
            title=row.title,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]


@router.get("/activation", response_model=ActivationMetricsResponse)
def list_activation_metrics(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    if refresh:
        run_activation_metrics_job(db)

    tenants = (
        db.query(Tenant)
        .filter(Tenant.is_demo_mode.is_(False))
        .order_by(Tenant.created_at.desc())
        .limit(limit)
        .all()
    )
    tenant_ids = [tenant.id for tenant in tenants]
    metrics = []
    metric_map: dict[int, ActivationMetric] = {}
    if tenant_ids:
        metrics = (
            db.query(ActivationMetric)
            .filter(ActivationMetric.tenant_id.in_(tenant_ids))
            .all()
        )
        metric_map = {metric.tenant_id: metric for metric in metrics}

    website_counts = {}
    alerts_counts = {}
    incidents_counts = {}
    if tenant_ids:
        website_counts = dict(
            db.query(Website.tenant_id, func.count(Website.id))
            .filter(
                Website.tenant_id.in_(tenant_ids),
                Website.deleted_at.is_(None),
            )
            .group_by(Website.tenant_id)
            .all()
        )
        alerts_counts = dict(
            db.query(NotificationRule.tenant_id, func.count(NotificationRule.id))
            .filter(NotificationRule.tenant_id.in_(tenant_ids))
            .group_by(NotificationRule.tenant_id)
            .all()
        )
        incident_query = db.query(Incident.tenant_id, func.count(Incident.id)).filter(
            Incident.tenant_id.in_(tenant_ids)
        )
        if hasattr(Incident, "is_demo"):
            incident_query = incident_query.filter(Incident.is_demo.is_(False))
        incidents_counts = dict(incident_query.group_by(Incident.tenant_id).all())

    items: list[ActivationMetricRead] = []
    time_to_first = []
    for tenant in tenants:
        metric = metric_map.get(tenant.id)
        notes = metric.notes_json if metric and isinstance(metric.notes_json, dict) else {}
        last_event_at = _parse_iso(notes.get("last_event_at"))
        days_since = notes.get("days_since_last_event")
        if metric and metric.time_to_first_event_seconds is not None:
            time_to_first.append(metric.time_to_first_event_seconds)
        items.append(
            ActivationMetricRead(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                tenant_slug=tenant.slug,
                tenant_created_at=tenant.created_at,
                time_to_first_event_seconds=metric.time_to_first_event_seconds if metric else None,
                onboarding_completed_at=metric.onboarding_completed_at if metric else None,
                first_alert_created_at=metric.first_alert_created_at if metric else None,
                first_incident_viewed_at=metric.first_incident_viewed_at if metric else None,
                first_prescription_applied_at=metric.first_prescription_applied_at if metric else None,
                activation_score=metric.activation_score if metric else 0,
                websites_count=int(website_counts.get(tenant.id, 0)),
                alerts_count=int(alerts_counts.get(tenant.id, 0)),
                incidents_count=int(incidents_counts.get(tenant.id, 0)),
                last_event_at=last_event_at,
                days_since_last_event=days_since if isinstance(days_since, int) else None,
            )
        )

    avg_time = None
    median_time = None
    if time_to_first:
        avg_time = sum(time_to_first) / len(time_to_first)
        sorted_times = sorted(time_to_first)
        mid = len(sorted_times) // 2
        if len(sorted_times) % 2:
            median_time = float(sorted_times[mid])
        else:
            median_time = (sorted_times[mid - 1] + sorted_times[mid]) / 2

    summary = ActivationSummary(
        total_tenants=len(items),
        tenants_with_events=sum(1 for item in items if item.time_to_first_event_seconds is not None),
        tenants_onboarded=sum(1 for item in items if item.onboarding_completed_at is not None),
        tenants_with_alerts=sum(1 for item in items if item.first_alert_created_at is not None),
        tenants_with_prescriptions=sum(
            1 for item in items if item.first_prescription_applied_at is not None
        ),
        average_time_to_first_event_seconds=avg_time,
        median_time_to_first_event_seconds=median_time,
    )

    if tenants:
        _audit_admin_action(
            db,
            tenant_id=tenants[0].id,
            username=current_user.username,
            event="admin.activation_list",
            request=request,
        )

    return ActivationMetricsResponse(items=items, summary=summary)


@router.post("/support/view-as", response_model=AdminSupportViewAsResponse)
def support_view_as(
    payload: AdminSupportViewAsRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_platform_admin()),
):
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reason is required")

    expires_delta = timedelta(minutes=settings.SUPPORT_VIEW_TOKEN_TTL_MINUTES)
    expires_at = datetime.utcnow() + expires_delta
    token = create_access_token(
        data={
            "sub": current_user.username,
            "support_mode": True,
            "support_readonly": True,
            "support_tenant_id": tenant.id,
        },
        expires_delta=expires_delta,
    )

    safe_reason = reason[:200]
    _audit_admin_action(
        db,
        tenant_id=tenant.id,
        username=current_user.username,
        event=f"admin.support_view_as:{safe_reason}",
        request=request,
    )

    return AdminSupportViewAsResponse(
        tenant_id=tenant.id,
        expires_at=expires_at,
        support_token=token,
    )
