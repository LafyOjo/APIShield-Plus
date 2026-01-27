from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.behaviour_events import BehaviourEvent
from app.models.notification_rules import NotificationRule
from app.models.onboarding_states import OnboardingState
from app.models.websites import Website


STEP_ORDER = [
    "create_website",
    "install_agent",
    "verify_events",
    "enable_geo_map",
    "create_alert",
    "finish",
]
STEP_SET = set(STEP_ORDER)


def _normalize_steps(steps: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for step in steps:
        if step in STEP_SET and step not in seen:
            normalized.append(step)
            seen.add(step)
    return normalized


def _next_step(completed: list[str]) -> str:
    for step in STEP_ORDER:
        if step not in completed:
            return step
    return STEP_ORDER[-1]


def get_or_create_onboarding_state(
    db: Session,
    tenant_id: int,
    *,
    created_by_user_id: int | None = None,
) -> OnboardingState:
    state = db.query(OnboardingState).filter(OnboardingState.tenant_id == tenant_id).first()
    if state:
        return state
    state = OnboardingState(
        tenant_id=tenant_id,
        current_step=STEP_ORDER[0],
        completed_steps_json=[],
        last_updated_at=utcnow(),
        created_by_user_id=created_by_user_id,
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def mark_step_completed(state: OnboardingState, step: str) -> None:
    if step not in STEP_SET:
        raise ValueError("Unknown onboarding step")
    completed = _normalize_steps(state.completed_steps_json or [])
    if step not in completed:
        completed.append(step)
    state.completed_steps_json = completed
    state.current_step = _next_step(completed)
    state.last_updated_at = utcnow()


def ensure_first_website(db: Session, state: OnboardingState) -> Website | None:
    if state.first_website_id:
        return None
    website = (
        db.query(Website)
        .filter(Website.tenant_id == state.tenant_id, Website.deleted_at.is_(None))
        .order_by(Website.created_at.asc())
        .first()
    )
    if not website:
        return None
    state.first_website_id = website.id
    mark_step_completed(state, "create_website")
    return website


def maybe_mark_alert_step(db: Session, state: OnboardingState) -> bool:
    completed = _normalize_steps(state.completed_steps_json or [])
    if "create_alert" in completed:
        return False
    rule_exists = (
        db.query(NotificationRule)
        .filter(NotificationRule.tenant_id == state.tenant_id)
        .first()
    )
    if not rule_exists:
        return False
    mark_step_completed(state, "create_alert")
    return True


def find_recent_event(
    db: Session,
    *,
    tenant_id: int,
    website_id: int | None = None,
    environment_id: int | None = None,
    window_minutes: int = 10,
) -> BehaviourEvent | None:
    window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
    query = db.query(BehaviourEvent).filter(
        BehaviourEvent.tenant_id == tenant_id,
        BehaviourEvent.ingested_at >= window_start,
    )
    if website_id is not None:
        query = query.filter(BehaviourEvent.website_id == website_id)
    if environment_id is not None:
        query = query.filter(BehaviourEvent.environment_id == environment_id)
    return query.order_by(BehaviourEvent.ingested_at.desc()).first()
