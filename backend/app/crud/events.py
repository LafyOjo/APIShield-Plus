# This module tracks user actions like login/logout and other
# notable events. It lets you create new rows, query recent
# activity, or pull out the latest login timestamp per user.

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.events import Event


# Insert a new Event row into the database. Stores who did it,
# the action string, and whether it succeeded. Commits the row
# so it’s durable, then refreshes and returns the new object.
def create_event(db: Session, username: str | None, action: str, success: bool) -> Event:
    event = Event(username=username, action=action, success=success)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# Fetch a list of events, optionally restricted to the last N
# hours. If hours is set, it only returns events newer than
# that threshold. Sorted so the newest events come first.
def get_events(db: Session, hours: int | None = None) -> list[Event]:
    query = db.query(Event)
    if hours is not None:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(Event.timestamp >= since)
    return query.order_by(Event.timestamp.desc()).all()


# For each user, find the most recent successful login event.
# Groups rows by username, picks the max timestamp, and then
# returns a dictionary mapping usernames to that datetime.
def get_last_logins(db: Session) -> dict[str, datetime]:
    rows = (
        db.query(Event.username, func.max(Event.timestamp))
        .filter(Event.action == "login", Event.success.is_(True))
        .group_by(Event.username)
        .all()
    )
    return {u: ts for u, ts in rows if u is not None}
