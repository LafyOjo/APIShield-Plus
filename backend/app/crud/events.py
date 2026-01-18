# This module tracks user actions like login/logout and other
# notable events. It lets you create new rows, query recent
# activity, or pull out the latest login timestamp per user.

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.privacy import hash_ip
from app.models.events import Event


# Insert a new Event row into the database. Stores who did it,
# the action string, and whether it succeeded. Commits the row
# so it’s durable, then refreshes and returns the new object.
def create_event(
    db: Session,
    tenant_id: int,
    username: str | None,
    action: str,
    success: bool,
    client_ip: str | None = None,
    ip_hash: str | None = None,
    user_agent: str | None = None,
    request_path: str | None = None,
    referrer: str | None = None,
    country_code: str | None = None,
    region: str | None = None,
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    asn: str | None = None,
    is_datacenter: bool | None = None,
) -> Event:
    if tenant_id is None:
        raise ValueError("tenant_id is required to create an event")
    if client_ip and ip_hash is None:
        try:
            ip_hash = hash_ip(tenant_id, client_ip)
        except ValueError:
            ip_hash = None
    event = Event(tenant_id=tenant_id, username=username, action=action, success=success)
    event.client_ip = client_ip
    event.ip_hash = ip_hash
    event.user_agent = user_agent
    event.request_path = request_path
    event.referrer = referrer
    event.country_code = country_code
    event.region = region
    event.city = city
    event.latitude = latitude
    event.longitude = longitude
    event.asn = asn
    event.is_datacenter = is_datacenter
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# Fetch a list of events, optionally restricted to the last N
# hours. If hours is set, it only returns events newer than
# that threshold. Sorted so the newest events come first.
def get_events(db: Session, tenant_id: int, hours: int | None = None) -> list[Event]:
    query = db.query(Event).filter(Event.tenant_id == tenant_id)
    if hours is not None:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(Event.timestamp >= since)
    return query.order_by(Event.timestamp.desc()).all()


# For each user, find the most recent successful login event.
# Groups rows by username, picks the max timestamp, and then
# returns a dictionary mapping usernames to that datetime.
def get_last_logins(db: Session, tenant_id: int) -> dict[str, datetime]:
    rows = (
        db.query(Event.username, func.max(Event.timestamp))
        .filter(
            Event.tenant_id == tenant_id,
            Event.action == "login",
            Event.success.is_(True),
        )
        .group_by(Event.username)
        .all()
    )
    return {u: ts for u, ts in rows if u is not None}
