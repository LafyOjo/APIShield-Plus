from datetime import datetime

from sqlalchemy.orm import Session

from app.core.privacy import hash_ip
from app.models.behaviour_events import BehaviourEvent


def create_behaviour_event(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    event_id: str,
    event_type: str,
    url: str,
    event_ts: datetime,
    ingested_at: datetime | None = None,
    path: str | None = None,
    referrer: str | None = None,
    session_id: str | None = None,
    visitor_id: str | None = None,
    meta: dict | None = None,
    ip_hash: str | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> BehaviourEvent:
    if tenant_id is None:
        raise ValueError("tenant_id is required")
    if not event_id:
        raise ValueError("event_id is required")
    if ip_hash is None and client_ip:
        try:
            ip_hash = hash_ip(tenant_id, client_ip)
        except ValueError:
            ip_hash = None
    event = BehaviourEvent(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        event_id=event_id,
        event_type=event_type,
        url=url,
        event_ts=event_ts,
        ingested_at=ingested_at or datetime.utcnow(),
        path=path,
        referrer=referrer,
        session_id=session_id,
        visitor_id=visitor_id,
        ip_hash=ip_hash,
        user_agent=user_agent,
        meta=meta,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_behaviour_event_by_event_id(
    db: Session,
    *,
    tenant_id: int,
    environment_id: int,
    event_id: str,
) -> BehaviourEvent | None:
    return (
        db.query(BehaviourEvent)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.environment_id == environment_id,
            BehaviourEvent.event_id == event_id,
        )
        .first()
    )
