from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.backfill_runs import BackfillRun


def get_active_backfill(db: Session, job_name: str) -> BackfillRun | None:
    return (
        db.query(BackfillRun)
        .filter(BackfillRun.job_name == job_name, BackfillRun.finished_at.is_(None))
        .order_by(desc(BackfillRun.started_at))
        .first()
    )


def start_backfill(db: Session, job_name: str) -> BackfillRun:
    run = BackfillRun(job_name=job_name, started_at=utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def resume_or_start_backfill(db: Session, job_name: str) -> BackfillRun:
    run = get_active_backfill(db, job_name)
    if run:
        return run
    return start_backfill(db, job_name)


def record_backfill_progress(db: Session, run: BackfillRun, last_id_processed: int) -> BackfillRun:
    run.last_id_processed = last_id_processed
    db.commit()
    db.refresh(run)
    return run


def finish_backfill(db: Session, run: BackfillRun) -> BackfillRun:
    run.finished_at = utcnow()
    db.commit()
    db.refresh(run)
    return run
