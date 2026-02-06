from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core.db import get_db
from app.models.job_dead_letters import JobDeadLetter
from app.schemas.queue import JobDeadLetterRead


router = APIRouter(prefix="/admin/queue", tags=["admin", "queue"])


@router.get("/dead-letters", response_model=list[JobDeadLetterRead])
def list_dead_letters(
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
    queue_name: str | None = Query(None),
    job_type: str | None = Query(None),
    tenant_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(JobDeadLetter)
    if queue_name:
        query = query.filter(JobDeadLetter.queue_name == queue_name)
    if job_type:
        query = query.filter(JobDeadLetter.job_type == job_type)
    if tenant_id is not None:
        query = query.filter(JobDeadLetter.tenant_id == tenant_id)
    return (
        query.order_by(JobDeadLetter.failed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
