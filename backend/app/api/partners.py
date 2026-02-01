from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.crud.subscriptions import get_active_subscription_for_tenant
from app.models.activation_metrics import ActivationMetric
from app.models.affiliates import AffiliateAttribution, AffiliateCommissionLedger
from app.models.partners import PartnerLead
from app.partners.dependencies import PartnerContext, require_partner_context
from app.schemas.partners import (
    PartnerCommissionRead,
    PartnerLeadRead,
    PartnerMeRead,
    PartnerMetricsRead,
)


router = APIRouter(prefix="/partners", tags=["partners"])


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _normalize_range(from_ts: datetime | None, to_ts: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    to_ts = to_ts or now
    from_ts = from_ts or (to_ts - timedelta(days=30))
    if from_ts > to_ts:
        from_ts, to_ts = to_ts, from_ts
    return from_ts, to_ts


def _tenant_ref(tenant_id: int) -> str:
    secret = settings.SECRET_KEY or "secret"
    digest = hashlib.sha256(f"{secret}:{tenant_id}".encode("utf-8")).hexdigest()[:10]
    return f"acct_{digest}"


@router.get("/me", response_model=PartnerMeRead)
def partner_me(ctx: PartnerContext = Depends(require_partner_context())):
    partner = ctx.partner
    return PartnerMeRead(
        partner_id=partner.id,
        partner_name=partner.name,
        partner_code=partner.code,
        role=ctx.partner_user.role,
        status=partner.status,
    )


@router.get("/metrics", response_model=PartnerMetricsRead)
def partner_metrics(
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
    ctx: PartnerContext = Depends(require_partner_context()),
):
    parsed_from = _parse_datetime(from_ts)
    parsed_to = _parse_datetime(to_ts)
    window_start, window_end = _normalize_range(parsed_from, parsed_to)

    leads = (
        db.query(func.count(PartnerLead.id))
        .filter(
            PartnerLead.partner_id == ctx.partner.id,
            PartnerLead.created_at >= window_start,
            PartnerLead.created_at <= window_end,
        )
        .scalar()
        or 0
    )

    signups = (
        db.query(func.count(AffiliateAttribution.id))
        .filter(
            AffiliateAttribution.partner_id == ctx.partner.id,
            AffiliateAttribution.first_touch_at >= window_start,
            AffiliateAttribution.first_touch_at <= window_end,
        )
        .scalar()
        or 0
    )

    activated = (
        db.query(func.count(ActivationMetric.tenant_id))
        .join(
            AffiliateAttribution,
            AffiliateAttribution.tenant_id == ActivationMetric.tenant_id,
        )
        .filter(
            AffiliateAttribution.partner_id == ctx.partner.id,
            AffiliateAttribution.first_touch_at >= window_start,
            AffiliateAttribution.first_touch_at <= window_end,
            ActivationMetric.time_to_first_event_seconds.isnot(None),
        )
        .scalar()
        or 0
    )

    conversion_query = (
        db.query(AffiliateCommissionLedger)
        .filter(
            AffiliateCommissionLedger.partner_id == ctx.partner.id,
            AffiliateCommissionLedger.created_at >= window_start,
            AffiliateCommissionLedger.created_at <= window_end,
            AffiliateCommissionLedger.status.in_(["pending", "earned", "paid"]),
        )
    )
    conversions = conversion_query.count()

    commission_pending = (
        db.query(func.coalesce(func.sum(AffiliateCommissionLedger.amount), 0))
        .filter(
            AffiliateCommissionLedger.partner_id == ctx.partner.id,
            AffiliateCommissionLedger.created_at >= window_start,
            AffiliateCommissionLedger.created_at <= window_end,
            AffiliateCommissionLedger.status == "pending",
        )
        .scalar()
        or 0
    )
    commission_earned = (
        db.query(func.coalesce(func.sum(AffiliateCommissionLedger.amount), 0))
        .filter(
            AffiliateCommissionLedger.partner_id == ctx.partner.id,
            AffiliateCommissionLedger.created_at >= window_start,
            AffiliateCommissionLedger.created_at <= window_end,
            AffiliateCommissionLedger.status == "earned",
        )
        .scalar()
        or 0
    )
    commission_paid = (
        db.query(func.coalesce(func.sum(AffiliateCommissionLedger.amount), 0))
        .filter(
            AffiliateCommissionLedger.partner_id == ctx.partner.id,
            AffiliateCommissionLedger.created_at >= window_start,
            AffiliateCommissionLedger.created_at <= window_end,
            AffiliateCommissionLedger.status == "paid",
        )
        .scalar()
        or 0
    )

    owed = float(commission_pending or 0) + float(commission_earned or 0)

    return PartnerMetricsRead(
        from_ts=window_start,
        to_ts=window_end,
        leads=int(leads),
        signups=int(signups),
        activated=int(activated),
        conversions=int(conversions),
        commission_pending=float(commission_pending or 0),
        commission_earned=float(commission_earned or 0),
        commission_paid=float(commission_paid or 0),
        commission_owed=owed,
    )


@router.get("/leads", response_model=list[PartnerLeadRead])
def list_partner_leads(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    ctx: PartnerContext = Depends(require_partner_context()),
):
    query = db.query(PartnerLead).filter(PartnerLead.partner_id == ctx.partner.id)
    if status:
        query = query.filter(PartnerLead.status == status)
    rows = query.order_by(PartnerLead.created_at.desc()).limit(limit).all()
    return [
        PartnerLeadRead(
            lead_id=row.lead_id,
            status=row.status,
            created_at=row.created_at,
            source_meta=row.source_meta_json if isinstance(row.source_meta_json, dict) else None,
            tenant_ref=_tenant_ref(row.associated_tenant_id)
            if row.associated_tenant_id
            else None,
        )
        for row in rows
    ]


@router.get("/commissions", response_model=list[PartnerCommissionRead])
def list_partner_commissions(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    ctx: PartnerContext = Depends(require_partner_context()),
):
    query = db.query(AffiliateCommissionLedger).filter(
        AffiliateCommissionLedger.partner_id == ctx.partner.id
    )
    if status:
        query = query.filter(AffiliateCommissionLedger.status == status)
    rows = query.order_by(AffiliateCommissionLedger.created_at.desc()).limit(limit).all()

    results: list[PartnerCommissionRead] = []
    for row in rows:
        subscription = get_active_subscription_for_tenant(db, row.tenant_id)
        plan_name = None
        subscription_status = None
        if subscription is not None:
            subscription_status = subscription.status
            if subscription.plan is not None:
                plan_name = subscription.plan.name
            elif subscription.plan_key:
                plan_name = subscription.plan_key
        results.append(
            PartnerCommissionRead(
                id=row.id,
                tenant_ref=_tenant_ref(row.tenant_id),
                plan_name=plan_name,
                subscription_status=subscription_status,
                conversion_date=row.created_at,
                amount=float(row.amount or 0),
                currency=row.currency,
                status=row.status,
                earned_at=row.earned_at,
                paid_at=row.paid_at,
            )
        )
    return results
