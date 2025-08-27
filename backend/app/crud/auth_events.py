# This module tracks logins, logouts, and related actions.
# Each event stores who did what, whether it worked, and the
# source (e.g. web, API). Useful for auditing and monitoring.

from sqlalchemy.orm import Session
from app.models.auth_events import AuthEvent


# Create a new AuthEvent row. We store the username (or None),
# the action string (like "login"), whether it succeeded, and
# where it came from. Committed to DB, then returned fresh.
def create_auth_event(
    db: Session, user: str | None, action: str, success: bool, source: str
) -> AuthEvent:
    event = AuthEvent(user=user, action=action, success=success, source=source)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# Fetch a paginated list of auth events. Default is the 50 most
# recent, but you can pass limit and offset to scroll through.
# Ordered descending by ID so newest appear first.
def get_auth_events(db: Session, limit: int = 50, offset: int = 0) -> list[AuthEvent]:
    return (
        db.query(AuthEvent)
        .order_by(AuthEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
