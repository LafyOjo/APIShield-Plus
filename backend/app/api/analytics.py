from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.event_types import MAX_META_BYTES, clamp_meta
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.behaviour_events import BehaviourEvent
from app.models.behaviour_sessions import BehaviourSession
from app.models.enums import RoleEnum
from app.schemas.analytics import (
    FunnelRequest,
    FunnelResponse,
    FunnelStepResult,
    SessionDetail,
    SessionEventItem,
    SessionListItem,
)
from app.schemas.common import PaginatedResponse
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id


def _safe_meta(meta):
    if isinstance(meta, dict):
        return clamp_meta(meta, MAX_META_BYTES)
    return None


def _normalize_range(from_ts: datetime | None, to_ts: datetime | None) -> tuple[datetime | None, datetime | None]:
    def _coerce(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    return _coerce(from_ts), _coerce(to_ts)


def _session_query(
    db: Session,
    *,
    tenant_id: int,
    website_id: int | None,
    environment_id: int | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
):
    query = db.query(BehaviourSession).filter(BehaviourSession.tenant_id == tenant_id)
    if website_id is not None:
        query = query.filter(BehaviourSession.website_id == website_id)
    if environment_id is not None:
        query = query.filter(BehaviourSession.environment_id == environment_id)
    if from_ts is not None:
        query = query.filter(BehaviourSession.started_at >= from_ts)
    if to_ts is not None:
        query = query.filter(BehaviourSession.started_at <= to_ts)
    return query


@router.get("/sessions", response_model=PaginatedResponse[SessionListItem])
def list_sessions(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = Query(None, alias="env_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    query = _session_query(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    total = query.count()
    sessions = (
        query.order_by(BehaviourSession.last_seen_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        SessionListItem(
            session_id=session.session_id,
            website_id=session.website_id,
            environment_id=session.environment_id,
            started_at=session.started_at,
            last_seen_at=session.last_seen_at,
            entry_path=session.entry_path,
            exit_path=session.exit_path,
            page_views=session.page_views,
            event_count=session.event_count,
            ip_hash=session.ip_hash,
            country_code=session.country_code,
        )
        for session in sessions
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session_detail(
    session_id: str,
    website_id: int | None = None,
    env_id: int | None = Query(None, alias="env_id"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    query = _session_query(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        from_ts=None,
        to_ts=None,
    ).filter(BehaviourSession.session_id == session_id)
    sessions = query.all()
    if not sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if len(sessions) > 1 and website_id is None and env_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple sessions found; provide env_id or website_id",
        )
    session = sessions[0]
    duration = 0
    if session.started_at and session.last_seen_at:
        delta = session.last_seen_at - session.started_at
        duration = max(0, int(delta.total_seconds()))
    return SessionDetail(
        session_id=session.session_id,
        website_id=session.website_id,
        environment_id=session.environment_id,
        started_at=session.started_at,
        last_seen_at=session.last_seen_at,
        entry_path=session.entry_path,
        exit_path=session.exit_path,
        page_views=session.page_views,
        event_count=session.event_count,
        ip_hash=session.ip_hash,
        country_code=session.country_code,
        duration_seconds=duration,
    )


@router.get("/sessions/{session_id}/events", response_model=PaginatedResponse[SessionEventItem])
def list_session_events(
    session_id: str,
    website_id: int | None = None,
    env_id: int | None = Query(None, alias="env_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    session_query = _session_query(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=env_id,
        from_ts=None,
        to_ts=None,
    ).filter(BehaviourSession.session_id == session_id)
    if not session_query.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    events_query = (
        db.query(BehaviourEvent)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.session_id == session_id,
        )
    )
    if website_id is not None:
        events_query = events_query.filter(BehaviourEvent.website_id == website_id)
    if env_id is not None:
        events_query = events_query.filter(BehaviourEvent.environment_id == env_id)

    total = events_query.count()
    events = (
        events_query.order_by(BehaviourEvent.event_ts.asc(), BehaviourEvent.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        SessionEventItem(
            event_id=event.event_id,
            event_type=event.event_type,
            event_ts=event.event_ts,
            url=event.url,
            path=event.path,
            referrer=event.referrer,
            session_id=event.session_id,
            meta=_safe_meta(event.meta),
        )
        for event in events
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/funnel", response_model=FunnelResponse)
def funnel_analytics(
    payload: FunnelRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    from_ts, to_ts = _normalize_range(payload.from_ts, payload.to_ts)
    steps = payload.steps
    step_filters = []
    for step in steps:
        condition = BehaviourEvent.event_type == step.type
        if step.path is not None:
            condition = condition & (BehaviourEvent.path == step.path)
        step_filters.append(condition)

    query = (
        db.query(
            BehaviourEvent.session_id,
            BehaviourEvent.event_type,
            BehaviourEvent.path,
            BehaviourEvent.event_ts,
            BehaviourEvent.id,
        )
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.website_id == payload.website_id,
            BehaviourEvent.environment_id == payload.env_id,
            BehaviourEvent.session_id.isnot(None),
        )
    )
    if step_filters:
        query = query.filter(or_(*step_filters))
    if from_ts is not None:
        query = query.filter(BehaviourEvent.event_ts >= from_ts)
    if to_ts is not None:
        query = query.filter(BehaviourEvent.event_ts <= to_ts)

    events = query.order_by(
        BehaviourEvent.session_id,
        BehaviourEvent.event_ts.asc(),
        BehaviourEvent.id.asc(),
    ).all()

    step_counts = [0 for _ in steps]
    current_session = None
    matched_index = 0

    def _finalize(index: int):
        for i in range(index):
            step_counts[i] += 1

    for event in events:
        session_id = event.session_id
        if session_id != current_session:
            if current_session is not None:
                _finalize(matched_index)
            current_session = session_id
            matched_index = 0
        if matched_index >= len(steps):
            continue
        step = steps[matched_index]
        if event.event_type != step.type:
            continue
        if step.path is not None and event.path != step.path:
            continue
        matched_index += 1

    if current_session is not None:
        _finalize(matched_index)

    results: list[FunnelStepResult] = []
    for idx, step in enumerate(steps):
        count = step_counts[idx]
        next_count = step_counts[idx + 1] if idx + 1 < len(step_counts) else 0
        conversion = None
        if idx + 1 < len(step_counts):
            conversion = (next_count / count) if count else 0.0
        results.append(
            FunnelStepResult(
                type=step.type,
                path=step.path,
                count=count,
                dropoff=max(count - next_count, 0),
                conversion_to_next=conversion,
            )
        )

    total_sessions = step_counts[0] if step_counts else 0
    return FunnelResponse(steps=results, total_sessions=total_sessions)
