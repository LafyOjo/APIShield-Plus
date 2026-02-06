from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.tenant_usage import TenantUsage


def _period_bounds(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    start = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
    if current.month == 12:
        end = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _get_or_create(db: Session, tenant_id: int, now: Optional[datetime] = None) -> TenantUsage:
    period_start, period_end = _period_bounds(now)
    usage = (
        db.query(TenantUsage)
        .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
        .first()
    )
    if usage:
        return usage
    usage = TenantUsage(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
    )
    db.add(usage)
    try:
        db.commit()
        db.refresh(usage)
        return usage
    except IntegrityError:
        db.rollback()
        return (
            db.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )


def get_or_create_current_period_usage(
    tenant_id: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if db is not None:
        return _get_or_create(db, tenant_id, now=now)
    with SessionLocal() as session:
        return _get_or_create(session, tenant_id, now=now)


def increment_events(
    tenant_id: int,
    count: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if count < 0:
        raise ValueError("count must be non-negative")
    session = db or SessionLocal()
    close_session = db is None
    try:
        period_start, _ = _period_bounds(now)
        _get_or_create(session, tenant_id, now=now)
        session.query(TenantUsage).filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.period_start == period_start,
        ).update(
            {
                TenantUsage.events_ingested: TenantUsage.events_ingested + count,
                TenantUsage.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        session.commit()
        return (
            session.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )
    finally:
        if close_session:
            session.close()


def increment_raw_events(
    tenant_id: int,
    count: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if count < 0:
        raise ValueError("count must be non-negative")
    session = db or SessionLocal()
    close_session = db is None
    try:
        period_start, _ = _period_bounds(now)
        _get_or_create(session, tenant_id, now=now)
        session.query(TenantUsage).filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.period_start == period_start,
        ).update(
            {
                TenantUsage.raw_events_stored: TenantUsage.raw_events_stored + count,
                TenantUsage.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        session.commit()
        return (
            session.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )
    finally:
        if close_session:
            session.close()


def increment_sampled_out(
    tenant_id: int,
    count: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if count < 0:
        raise ValueError("count must be non-negative")
    session = db or SessionLocal()
    close_session = db is None
    try:
        period_start, _ = _period_bounds(now)
        _get_or_create(session, tenant_id, now=now)
        session.query(TenantUsage).filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.period_start == period_start,
        ).update(
            {
                TenantUsage.events_sampled_out: TenantUsage.events_sampled_out + count,
                TenantUsage.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        session.commit()
        return (
            session.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )
    finally:
        if close_session:
            session.close()


def increment_aggregate_rows(
    tenant_id: int,
    count: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if count < 0:
        raise ValueError("count must be non-negative")
    session = db or SessionLocal()
    close_session = db is None
    try:
        period_start, _ = _period_bounds(now)
        _get_or_create(session, tenant_id, now=now)
        session.query(TenantUsage).filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.period_start == period_start,
        ).update(
            {
                TenantUsage.aggregate_rows_stored: TenantUsage.aggregate_rows_stored + count,
                TenantUsage.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        session.commit()
        return (
            session.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )
    finally:
        if close_session:
            session.close()


def increment_storage(
    tenant_id: int,
    byte_count: int,
    *,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> TenantUsage:
    if byte_count < 0:
        raise ValueError("byte_count must be non-negative")
    session = db or SessionLocal()
    close_session = db is None
    try:
        period_start, _ = _period_bounds(now)
        _get_or_create(session, tenant_id, now=now)
        session.query(TenantUsage).filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.period_start == period_start,
        ).update(
            {
                TenantUsage.storage_bytes: TenantUsage.storage_bytes + byte_count,
                TenantUsage.updated_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
        session.commit()
        return (
            session.query(TenantUsage)
            .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
            .first()
        )
    finally:
        if close_session:
            session.close()
