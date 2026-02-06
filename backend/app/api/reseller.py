from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.billing.catalog import get_plan_name, normalize_plan_key
from app.core.config import settings
from app.core.db import get_db
from app.crud.audit import create_audit_log
from app.crud.feature_entitlements import seed_entitlements_from_plan
from app.crud.invites import create_invite
from app.crud.plans import get_plan_by_name
from app.crud.resellers import create_managed_tenant, get_reseller_account, list_managed_tenants
from app.crud.tenants import create_tenant
from app.models.activation_metrics import ActivationMetric
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import RoleEnum
from app.models.subscriptions import Subscription
from app.partners.dependencies import PartnerContext, require_partner_context
from app.schemas.resellers import (
    ResellerManagedTenantList,
    ResellerManagedTenantRead,
    ResellerTenantCreate,
    ResellerTenantProvisioned,
    ResellerTenantRead,
    ResellerAccountRead,
)


router = APIRouter(prefix="/reseller", tags=["reseller"])

ALLOWED_RESELLER_ROLES = {"admin", "reseller_admin"}


def _require_reseller_admin(ctx: PartnerContext) -> None:
    if ctx.partner_user.role not in ALLOWED_RESELLER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reseller admin required")


def _resolve_plan(db: Session, plan_key: str | None):
    normalized = normalize_plan_key(plan_key) or "free"
    plan_name = get_plan_name(normalized)
    if not plan_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported plan key")
    plan = get_plan_by_name(db, plan_name)
    if not plan:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan not configured")
    return normalized, plan


def _reseller_account_or_403(db: Session, *, partner_id: int):
    account = get_reseller_account(db, partner_id=partner_id)
    if not account or not account.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reseller account not enabled")
    return account


def _build_tenant_read(
    *,
    tenant_id: int,
    tenant_name: str,
    tenant_slug: str,
    status: str,
    billing_mode: str,
    plan_name: str | None,
    subscription_status: str | None,
    activation_score: int | None,
    last_event_at: datetime | None,
    ingest_24h: int,
) -> ResellerTenantRead:
    return ResellerTenantRead(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        status=status,
        plan_name=plan_name,
        subscription_status=subscription_status,
        activation_score=activation_score,
        last_event_at=last_event_at,
        ingest_24h=ingest_24h,
        billing_mode=billing_mode,
    )


@router.post("/tenants", response_model=ResellerTenantProvisioned, status_code=status.HTTP_201_CREATED)
def create_reseller_tenant(
    payload: ResellerTenantCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: PartnerContext = Depends(require_partner_context()),
):
    _require_reseller_admin(ctx)
    account = _reseller_account_or_403(db, partner_id=ctx.partner.id)

    allowed_plans = account.allowed_plans if isinstance(account.allowed_plans, list) else None
    plan_key, plan = _resolve_plan(db, payload.plan_key)
    if allowed_plans is not None:
        allowed_normalized = {normalize_plan_key(p) for p in allowed_plans if p}
        if plan_key not in allowed_normalized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Plan not allowed for reseller")

    tenant = create_tenant(
        db,
        name=payload.name,
        slug=payload.slug,
        created_by_user_id=None,
    )

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        plan_key=plan_key,
        provider="reseller",
        status="active",
    )
    db.add(subscription)
    db.commit()

    seed_entitlements_from_plan(db, tenant.id, plan)
    managed = create_managed_tenant(db, partner_id=ctx.partner.id, tenant_id=tenant.id, status="active")

    invite_email = None
    invite_token = None
    if payload.owner_email:
        invite_email = payload.owner_email
        invite, token = create_invite(
            db,
            tenant_id=tenant.id,
            email=payload.owner_email,
            role=RoleEnum.OWNER,
            created_by_user_id=ctx.user.id,
        )
        if settings.INVITE_TOKEN_RETURN_IN_RESPONSE:
            invite_token = token
        create_audit_log(
            db,
            tenant_id=tenant.id,
            username=ctx.user.username,
            event=f"reseller.invite_created:{invite.email}",
            request=request,
        )

    create_audit_log(
        db,
        tenant_id=tenant.id,
        username=ctx.user.username,
        event=f"reseller.tenant_created:{tenant.slug}",
        request=request,
    )

    activation = (
        db.query(ActivationMetric)
        .filter(ActivationMetric.tenant_id == tenant.id)
        .first()
    )

    ingest_24h = (
        db.query(func.count(BehaviourEvent.id))
        .filter(
            BehaviourEvent.tenant_id == tenant.id,
            BehaviourEvent.ingested_at >= datetime.utcnow() - timedelta(hours=24),
        )
        .scalar()
        or 0
    )

    tenant_read = _build_tenant_read(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        status=managed.status,
        billing_mode=account.billing_mode,
        plan_name=plan.name,
        subscription_status=subscription.status,
        activation_score=activation.activation_score if activation else None,
        last_event_at=None,
        ingest_24h=int(ingest_24h),
    )

    return ResellerTenantProvisioned(
        tenant=tenant_read,
        invite_email=invite_email,
        invite_token=invite_token,
    )


@router.get("/tenants", response_model=ResellerManagedTenantList)
def list_reseller_tenants(
    db: Session = Depends(get_db),
    ctx: PartnerContext = Depends(require_partner_context()),
):
    account = _reseller_account_or_403(db, partner_id=ctx.partner.id)
    tenants = list_managed_tenants(db, partner_id=ctx.partner.id)

    tenant_ids = [row.tenant_id for row in tenants]
    activation_map = {}
    if tenant_ids:
        activation_rows = (
            db.query(ActivationMetric)
            .filter(ActivationMetric.tenant_id.in_(tenant_ids))
            .all()
        )
        activation_map = {row.tenant_id: row for row in activation_rows}

    ingest_map = {}
    if tenant_ids:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        ingest_map = dict(
            db.query(BehaviourEvent.tenant_id, func.count(BehaviourEvent.id))
            .filter(BehaviourEvent.tenant_id.in_(tenant_ids), BehaviourEvent.ingested_at >= cutoff)
            .group_by(BehaviourEvent.tenant_id)
            .all()
        )

    from app.models.tenants import Tenant
    from app.crud.subscriptions import get_latest_subscription_for_tenant

    results: list[ResellerManagedTenantRead] = []
    for row in tenants:
        tenant_record = db.query(Tenant).filter(Tenant.id == row.tenant_id).first()
        if not tenant_record:
            continue
        subscription = get_latest_subscription_for_tenant(db, tenant_record.id)
        plan_name = subscription.plan.name if subscription and subscription.plan else None
        activation = activation_map.get(tenant_record.id)
        last_event_at = None
        if activation and isinstance(activation.notes_json, dict):
            last_event_at = activation.notes_json.get("last_event_at")
            if isinstance(last_event_at, str):
                try:
                    last_event_at = datetime.fromisoformat(last_event_at.replace("Z", "+00:00"))
                    if last_event_at.tzinfo is not None:
                        last_event_at = last_event_at.replace(tzinfo=None)
                except ValueError:
                    last_event_at = None
        ingest_24h = int(ingest_map.get(tenant_record.id, 0) or 0)
        results.append(
            ResellerManagedTenantRead(
                tenant_id=tenant_record.id,
                tenant_name=tenant_record.name,
                tenant_slug=tenant_record.slug,
                status=row.status,
                plan_name=plan_name,
                subscription_status=subscription.status if subscription else None,
                activation_score=activation.activation_score if activation else None,
                last_event_at=last_event_at,
                ingest_24h=ingest_24h,
                billing_mode=account.billing_mode,
                created_at=row.created_at,
            )
        )

    return ResellerManagedTenantList(
        account=ResellerAccountRead(
            billing_mode=account.billing_mode,
            allowed_plans=account.allowed_plans if isinstance(account.allowed_plans, list) else None,
            is_enabled=account.is_enabled,
        ),
        tenants=results,
    )
