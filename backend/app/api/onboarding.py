from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.onboarding import (
    STEP_ORDER,
    ensure_first_website,
    find_recent_event,
    get_or_create_onboarding_state,
    mark_step_completed,
    maybe_mark_alert_step,
)
from app.core.onboarding_emails import queue_upgrade_nudge
from app.crud.websites import get_website
from app.crud.audit import create_audit_log
from app.models.enums import RoleEnum
from app.schemas.onboarding import (
    FeatureLockedEvent,
    OnboardingStateRead,
    OnboardingStepComplete,
)
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant
from app.tenancy.errors import TenantNotFound


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _serialize_state(state) -> OnboardingStateRead:
    return OnboardingStateRead(
        tenant_id=state.tenant_id,
        current_step=state.current_step,
        completed_steps=state.completed_steps_json or [],
        last_updated_at=state.last_updated_at,
        verified_event_received_at=state.verified_event_received_at,
        first_website_id=state.first_website_id,
        created_by_user_id=state.created_by_user_id,
        created_at=getattr(state, "created_at", None),
        updated_at=getattr(state, "updated_at", None),
    )


def _auto_verify_events(db, state) -> bool:
    if "verify_events" in (state.completed_steps_json or []):
        return False
    if not state.first_website_id:
        return False
    event = find_recent_event(
        db,
        tenant_id=state.tenant_id,
        website_id=state.first_website_id,
    )
    if not event:
        return False
    mark_step_completed(state, "verify_events")
    state.verified_event_received_at = event.ingested_at
    return True


@router.get("/state", response_model=OnboardingStateRead)
def get_onboarding_state(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    state = get_or_create_onboarding_state(db, membership.tenant_id, created_by_user_id=ctx.user_id)
    touched = False
    if ensure_first_website(db, state):
        touched = True
    if maybe_mark_alert_step(db, state):
        touched = True
    if _auto_verify_events(db, state):
        touched = True
    if touched:
        db.commit()
        db.refresh(state)
    return _serialize_state(state)


@router.post("/complete-step", response_model=OnboardingStateRead)
def complete_step(
    payload: OnboardingStepComplete,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.ANALYST], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    step = (payload.step or "").strip()
    if step not in STEP_ORDER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown onboarding step")

    state = get_or_create_onboarding_state(db, membership.tenant_id, created_by_user_id=ctx.user_id)

    if step == "create_website":
        if not payload.website_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="website_id is required")
        try:
            website = get_website(db, membership.tenant_id, payload.website_id)
        except TenantNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
        if not state.first_website_id:
            state.first_website_id = website.id
    if step == "verify_events":
        website_id = payload.website_id or state.first_website_id
        if not website_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="website_id is required")
        if not state.first_website_id:
            try:
                website = get_website(db, membership.tenant_id, website_id)
            except TenantNotFound as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
            state.first_website_id = website.id
        event = find_recent_event(
            db,
            tenant_id=membership.tenant_id,
            website_id=website_id,
            environment_id=payload.environment_id,
        )
        if not event:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No recent events detected yet. Please install the agent and retry.",
            )
        state.verified_event_received_at = event.ingested_at
    if step == "install_agent" and payload.website_id and not state.first_website_id:
        try:
            website = get_website(db, membership.tenant_id, payload.website_id)
        except TenantNotFound as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found") from exc
        state.first_website_id = website.id

    mark_step_completed(state, step)
    db.commit()
    db.refresh(state)
    return _serialize_state(state)


@router.post("/feature-locked")
def feature_locked(
    payload: FeatureLockedEvent,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    feature_key = (payload.feature_key or "").strip()
    if not feature_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="feature_key is required")
    action = (payload.action or "shown").strip() or "shown"
    source = (payload.source or "").strip()
    event_suffix = f"{feature_key}:{source}" if source else feature_key
    create_audit_log(
        db,
        tenant_id=membership.tenant_id,
        username=current_user.email,
        event=f"paywall.{action}:{event_suffix}",
    )
    queue_upgrade_nudge(
        db,
        tenant_id=membership.tenant_id,
        user_id=current_user.id,
        feature_key=feature_key,
        source=payload.source or action,
    )
    return {"ok": True}
