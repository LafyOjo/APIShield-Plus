from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.retention_runs import RetentionRun


def list_retention_runs(
    db: Session,
    tenant_id: int,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 200,
) -> list[RetentionRun]:
    query = (
        db.query(RetentionRun)
        .filter(RetentionRun.tenant_id == tenant_id)
        .order_by(RetentionRun.started_at.desc())
    )
    if from_ts is not None:
        query = query.filter(RetentionRun.started_at >= from_ts)
    if to_ts is not None:
        query = query.filter(RetentionRun.started_at <= to_ts)
    if limit:
        query = query.limit(limit)
    return query.all()
