from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core.db import get_db
from app.core.time import utcnow
from app.models.job_dead_letters import JobDeadLetter
from app.models.job_queue import JobQueue
from app.schemas.queue import JobDeadLetterRead, JobQueueStatsRead


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


@router.get("/stats", response_model=list[JobQueueStatsRead])
def queue_stats(
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    now = utcnow()
    now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
    window_start = now - timedelta(hours=1)
    queues = ("critical", "standard", "bulk")
    stats: list[JobQueueStatsRead] = []

    for queue_name in queues:
        queued = (
            db.query(JobQueue)
            .filter(JobQueue.queue_name == queue_name, JobQueue.status == "queued")
            .count()
        )
        running = (
            db.query(JobQueue)
            .filter(JobQueue.queue_name == queue_name, JobQueue.status == "running")
            .count()
        )
        succeeded_last_hour = (
            db.query(JobQueue)
            .filter(
                JobQueue.queue_name == queue_name,
                JobQueue.status == "succeeded",
                JobQueue.finished_at >= window_start,
            )
            .count()
        )
        retrying = (
            db.query(JobQueue)
            .filter(
                JobQueue.queue_name == queue_name,
                JobQueue.status.in_(["queued", "running"]),
                JobQueue.attempt_count > 1,
            )
            .count()
        )
        failed_last_hour = (
            db.query(JobDeadLetter)
            .filter(
                JobDeadLetter.queue_name == queue_name,
                JobDeadLetter.failed_at >= window_start,
            )
            .count()
        )
        dead_letters_total = (
            db.query(JobDeadLetter).filter(JobDeadLetter.queue_name == queue_name).count()
        )

        queued_created = (
            db.query(JobQueue.created_at)
            .filter(JobQueue.queue_name == queue_name, JobQueue.status == "queued")
            .all()
        )
        queue_ages: list[float] = []
        for (created_at,) in queued_created:
            if created_at is None:
                continue
            if created_at.tzinfo is not None:
                created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
            queue_ages.append(max(0.0, (now_naive - created_at).total_seconds()))
        avg_queue_age_seconds = sum(queue_ages) / len(queue_ages) if queue_ages else 0.0

        stats.append(
            JobQueueStatsRead(
                queue_name=queue_name,
                queued=queued,
                running=running,
                succeeded_last_hour=succeeded_last_hour,
                failed_last_hour=failed_last_hour,
                retrying=retrying,
                avg_queue_age_seconds=round(avg_queue_age_seconds, 3),
                dead_letters_total=dead_letters_total,
            )
        )

    return stats
