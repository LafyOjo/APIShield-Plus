from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_platform_admin
from app.core.db import get_db
from app.core.referrals import build_share_url, generate_referral_code
from app.crud.referrals import (
    get_effective_program_config,
    get_program_config,
    get_credit_balance,
    list_referral_invites,
    list_redemptions_for_tenant,
    upsert_program_config,
    create_referral_invite,
)
from app.crud.audit import create_audit_log
from app.models.enums import RoleEnum
from app.schemas.referrals import (
    ReferralInviteCreate,
    ReferralInviteRead,
    ReferralInviteResponse,
    ReferralProgramConfigRead,
    ReferralProgramConfigUpdate,
    ReferralRedemptionRead,
    ReferralSummary,
)
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/referrals", tags=["referrals"])


def _serialize_config(config) -> ReferralProgramConfigRead:
    return ReferralProgramConfigRead(
        is_enabled=bool(config.is_enabled),
        reward_type=config.reward_type,
        reward_value=float(config.reward_value or 0),
        eligibility_rules=config.eligibility_rules_json or {},
        fraud_limits=config.fraud_limits_json or {},
        updated_at=config.updated_at,
    )


@router.get("/config", response_model=ReferralProgramConfigRead)
def get_referral_config(
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    config = get_program_config(db)
    if not config:
        config = get_effective_program_config(db)
    return _serialize_config(config)


@router.post("/config", response_model=ReferralProgramConfigRead)
def upsert_referral_config(
    payload: ReferralProgramConfigUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    updates = payload.dict(exclude_unset=True)
    if "reward_type" in updates:
        allowed = {"credit_gbp", "discount_percent", "free_month"}
        if updates["reward_type"] not in allowed:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid reward type")
    if "reward_value" in updates and updates["reward_value"] is not None:
        if updates["reward_value"] < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid reward value")
    config = upsert_program_config(db, payload=updates)
    return _serialize_config(config)


@router.get("/summary", response_model=ReferralSummary)
def get_referral_summary(
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = int(ctx.tenant_id)
    pending = 0
    applied = 0
    redemptions = list_redemptions_for_tenant(db, tenant_id=tenant_id)
    for redemption in redemptions:
        if redemption.status == "pending":
            pending += 1
        if redemption.status == "applied":
            applied += 1
    return ReferralSummary(
        credit_balance=get_credit_balance(db, tenant_id=tenant_id),
        pending_redemptions=pending,
        applied_redemptions=applied,
    )


@router.post("/invites", response_model=ReferralInviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: ReferralInviteCreate,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    config = get_effective_program_config(db)
    if not config.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Referral program disabled")

    now = datetime.utcnow()
    expires_at = payload.expires_at
    if expires_at is None and payload.expires_in_days:
        expires_at = now + timedelta(days=payload.expires_in_days)
    if expires_at is None:
        expires_at = now + timedelta(days=30)
    max_uses = payload.max_uses or 20

    code = generate_referral_code()
    invite = create_referral_invite(
        db,
        tenant_id=int(ctx.tenant_id),
        created_by_user_id=ctx.user_id,
        code=code,
        expires_at=expires_at,
        max_uses=max_uses,
    )
    create_audit_log(
        db,
        tenant_id=int(ctx.tenant_id),
        username=None,
        event=f"referral.invite.created:{invite.id}",
    )
    invite_read = ReferralInviteRead(
        id=invite.id,
        code=invite.code,
        status=invite.status,
        uses_count=invite.uses_count,
        max_uses=invite.max_uses,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        share_url=build_share_url(invite.code),
    )
    return ReferralInviteResponse(invite=invite_read, share_url=build_share_url(invite.code))


@router.get("/invites", response_model=list[ReferralInviteRead])
def list_invites(
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = int(ctx.tenant_id)
    invites = list_referral_invites(db, tenant_id=tenant_id)
    return [
        ReferralInviteRead(
            id=invite.id,
            code=invite.code,
            status=invite.status,
            uses_count=invite.uses_count,
            max_uses=invite.max_uses,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            share_url=build_share_url(invite.code),
        )
        for invite in invites
    ]


@router.get("/redemptions", response_model=list[ReferralRedemptionRead])
def list_redemptions(
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = int(ctx.tenant_id)
    redemptions = list_redemptions_for_tenant(db, tenant_id=tenant_id)
    return [
        ReferralRedemptionRead(
            id=redemption.id,
            invite_id=redemption.invite_id,
            new_tenant_id=redemption.new_tenant_id,
            status=redemption.status,
            redeemed_at=redemption.redeemed_at,
            reward_applied_at=redemption.reward_applied_at,
            reason=redemption.reason,
        )
        for redemption in redemptions
    ]
