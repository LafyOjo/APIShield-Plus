from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.user_tour_states import UserTourState


def _normalize(values: list[str]) -> list[str]:
    seen = set()
    normalized = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def get_or_create_tour_state(
    db: Session,
    *,
    user_id: int,
    tenant_id: int,
) -> UserTourState:
    state = (
        db.query(UserTourState)
        .filter(
            UserTourState.user_id == user_id,
            UserTourState.tenant_id == tenant_id,
        )
        .first()
    )
    if state:
        return state
    state = UserTourState(
        user_id=user_id,
        tenant_id=tenant_id,
        tours_completed_json=[],
        tours_dismissed_json=[],
        last_updated_at=utcnow(),
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def update_tour_state(
    state: UserTourState,
    *,
    complete: list[str] | None = None,
    dismiss: list[str] | None = None,
    reset: list[str] | None = None,
) -> UserTourState:
    completed = set(state.tours_completed_json or [])
    dismissed = set(state.tours_dismissed_json or [])

    for item in _normalize(complete or []):
        completed.add(item)
        dismissed.discard(item)
    for item in _normalize(dismiss or []):
        if item not in completed:
            dismissed.add(item)
    for item in _normalize(reset or []):
        completed.discard(item)
        dismissed.discard(item)

    state.tours_completed_json = sorted(completed)
    state.tours_dismissed_json = sorted(dismissed)
    state.last_updated_at = utcnow()
    return state
