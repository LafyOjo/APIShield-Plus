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


def upsert_behaviour_sessions_bulk(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    updates: list[dict],
    commit: bool = True,
) -> int:
    if not updates:
        return 0
    session_ids = {item.get("session_id") for item in updates if item.get("session_id")}
    if not session_ids:
        return 0
    existing_sessions = (
        db.query(BehaviourSession)
        .filter(
            BehaviourSession.tenant_id == tenant_id,
            BehaviourSession.environment_id == environment_id,
            BehaviourSession.session_id.in_(session_ids),
        )
        .all()
    )
    existing_map = {session.session_id: session for session in existing_sessions}
    new_sessions: list[BehaviourSession] = []
    touched = 0

    for update in updates:
        session_id = update.get("session_id")
        if not session_id:
            continue
        event_type = update.get("event_type")
        event_ts = update.get("event_ts")
        path = update.get("path")
        ip_hash = update.get("ip_hash")
        normalized_ts = event_ts
        if normalized_ts and getattr(normalized_ts, "tzinfo", None) is not None:
            normalized_ts = normalized_ts.astimezone(timezone.utc).replace(tzinfo=None)
        session = existing_map.get(session_id)
        if session is None:
            started_at = normalized_ts or datetime.now(timezone.utc)
            new_sessions.append(
                BehaviourSession(
                    tenant_id=tenant_id,
                    website_id=website_id,
                    environment_id=environment_id,
                    session_id=session_id,
                    started_at=started_at,
                    last_seen_at=normalized_ts or started_at,
                    event_count=1,
                    page_views=1 if event_type == "page_view" else 0,
                    ip_hash=ip_hash,
                    entry_path=path,
                    exit_path=path,
                )
            )
            touched += 1
            continue
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
        touched += 1

    if new_sessions:
        db.bulk_save_objects(new_sessions)
    if commit:
        db.commit()
    return touched
