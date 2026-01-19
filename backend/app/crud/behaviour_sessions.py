from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.behaviour_sessions import BehaviourSession


def get_behaviour_session(
    db: Session,
    *,
    tenant_id: int,
    environment_id: int,
    session_id: str,
) -> BehaviourSession | None:
    return (
        db.query(BehaviourSession)
        .filter(
            BehaviourSession.tenant_id == tenant_id,
            BehaviourSession.environment_id == environment_id,
            BehaviourSession.session_id == session_id,
        )
        .first()
    )


def upsert_behaviour_session(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    session_id: str,
    event_type: str,
    event_ts: datetime,
    path: str | None,
    ip_hash: str | None = None,
) -> BehaviourSession:
    if not session_id:
        raise ValueError("session_id is required")

    normalized_ts = event_ts
    if normalized_ts and normalized_ts.tzinfo is not None:
        normalized_ts = normalized_ts.astimezone(timezone.utc).replace(tzinfo=None)

    session = get_behaviour_session(
        db,
        tenant_id=tenant_id,
        environment_id=environment_id,
        session_id=session_id,
    )
    if not session:
        started_at = normalized_ts
        last_seen_at = normalized_ts
        session = BehaviourSession(
            tenant_id=tenant_id,
            website_id=website_id,
            environment_id=environment_id,
            session_id=session_id,
            started_at=started_at,
            last_seen_at=last_seen_at,
            event_count=1,
            page_views=1 if event_type == "page_view" else 0,
            ip_hash=ip_hash,
            entry_path=path,
            exit_path=path,
        )
        db.add(session)
    else:
        session.event_count = (session.event_count or 0) + 1
        if event_type == "page_view":
            session.page_views = (session.page_views or 0) + 1
        if normalized_ts and (session.last_seen_at is None or normalized_ts > session.last_seen_at):
            session.last_seen_at = normalized_ts
        if session.ip_hash is None and ip_hash:
            session.ip_hash = ip_hash
        if session.entry_path is None and path:
            session.entry_path = path
        if path:
            session.exit_path = path

    db.commit()
    db.refresh(session)
    return session
