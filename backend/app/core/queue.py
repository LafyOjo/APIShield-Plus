from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import allow
from app.core.metrics import record_queue_retry
from app.core.time import utcnow
from app.models.job_dead_letters import JobDeadLetter
from app.models.job_queue import JobQueue

QueueHandler = Callable[[Session, dict[str, Any]], Any]

QUEUE_NAMES = {"critical", "standard", "bulk"}
DEFAULT_QUEUE = "standard"

JOB_TYPE_QUEUE: dict[str, str] = {
    "notification_send": "critical",
    "incident_update": "critical",
    "trust_scoring": "standard",
    "revenue_leak": "standard",
    "geo_enrich": "bulk",
    "data_exports": "bulk",
    "marketplace_seed": "bulk",
}


@dataclass
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int


JOB_RETRY_POLICIES: dict[str, RetryPolicy] = {
    "notification_send": RetryPolicy(max_attempts=5, base_delay_seconds=5, max_delay_seconds=60),
    "incident_update": RetryPolicy(max_attempts=4, base_delay_seconds=10, max_delay_seconds=120),
    "trust_scoring": RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
    "revenue_leak": RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300),
    "geo_enrich": RetryPolicy(max_attempts=2, base_delay_seconds=120, max_delay_seconds=900),
    "data_exports": RetryPolicy(max_attempts=3, base_delay_seconds=300, max_delay_seconds=3600),
    "marketplace_seed": RetryPolicy(max_attempts=2, base_delay_seconds=300, max_delay_seconds=1800),
}

DEFAULT_RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300)

_JOB_HANDLERS: dict[str, QueueHandler] = {}


def register_job_handler(job_type: str, handler: QueueHandler) -> None:
    _JOB_HANDLERS[job_type] = handler


def clear_job_handlers() -> None:
    _JOB_HANDLERS.clear()


def get_job_handler(job_type: str) -> QueueHandler | None:
    return _JOB_HANDLERS.get(job_type)


def _normalize_queue_name(queue_name: str | None, job_type: str | None) -> str:
    if queue_name:
        name = queue_name.strip().lower()
        if name in QUEUE_NAMES:
            return name
    if job_type and job_type in JOB_TYPE_QUEUE:
        return JOB_TYPE_QUEUE[job_type]
    return DEFAULT_QUEUE


def _policy_for_job(job: JobQueue) -> RetryPolicy:
    return JOB_RETRY_POLICIES.get(job.job_type, DEFAULT_RETRY_POLICY)


def _backoff_seconds(policy: RetryPolicy, attempt: int) -> int:
    multiplier = 2 ** max(attempt - 1, 0)
    delay = policy.base_delay_seconds * multiplier
    return min(delay, policy.max_delay_seconds)


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    tenant_id: int | None = None,
    queue_name: str | None = None,
    priority: int | None = None,
    run_at: datetime | None = None,
    max_attempts: int | None = None,
) -> JobQueue:
    queue_name = _normalize_queue_name(queue_name, job_type)
    job = JobQueue(
        queue_name=queue_name,
        job_type=job_type,
        tenant_id=tenant_id,
        payload_json=payload or {},
        priority=priority if priority is not None else 100,
        run_at=run_at or utcnow(),
        max_attempts=max_attempts,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _tenant_fairness_limits(queue_name: str) -> tuple[int | None, int | None, int | None]:
    if queue_name == "standard":
        return (
            settings.QUEUE_TENANT_RPM_STANDARD,
            settings.QUEUE_TENANT_BURST_STANDARD,
            settings.QUEUE_TENANT_MAX_IN_FLIGHT_STANDARD,
        )
    if queue_name == "bulk":
        return (
            settings.QUEUE_TENANT_RPM_BULK,
            settings.QUEUE_TENANT_BURST_BULK,
            settings.QUEUE_TENANT_MAX_IN_FLIGHT_BULK,
        )
    return (None, None, None)


def _throttle_delay(queue_name: str, tenant_id: int, rpm: int, burst: int) -> int | None:
    if rpm <= 0 or burst <= 0:
        return None
    allowed, retry_after = allow(
        f"queue:{queue_name}:tenant:{tenant_id}",
        capacity=burst,
        refill_rate_per_sec=rpm / 60.0,
    )
    if allowed:
        return None
    return max(1, retry_after)


def claim_jobs(
    db: Session,
    *,
    queue_name: str,
    limit: int,
    worker_id: str,
) -> list[JobQueue]:
    now = utcnow()
    lock_timeout = timedelta(seconds=max(1, settings.JOB_QUEUE_LOCK_TIMEOUT_SECONDS))
    lock_cutoff = now - lock_timeout
    candidates = (
        db.query(JobQueue)
        .filter(
            JobQueue.queue_name == queue_name,
            JobQueue.status == "queued",
            JobQueue.run_at <= now,
            or_(JobQueue.locked_at.is_(None), JobQueue.locked_at < lock_cutoff),
        )
        .order_by(JobQueue.priority.asc(), JobQueue.run_at.asc(), JobQueue.created_at.asc())
        .limit(limit * 5)
        .all()
    )

    rpm, burst, max_per_tenant = _tenant_fairness_limits(queue_name)
    selected: list[JobQueue] = []
    per_tenant_counts: dict[int, int] = {}

    for job in candidates:
        if len(selected) >= limit:
            break
        tenant_id = job.tenant_id
        if tenant_id is not None and max_per_tenant:
            if per_tenant_counts.get(tenant_id, 0) >= max_per_tenant:
                continue
        if tenant_id is not None and rpm is not None and burst is not None:
            delay = _throttle_delay(queue_name, tenant_id, rpm, burst)
            if delay is not None:
                job.run_at = now + timedelta(seconds=delay)
                job.last_error = "tenant_throttled"
                continue

        job.status = "running"
        job.locked_at = now
        job.locked_by = worker_id
        job.last_attempt_at = now
        job.attempt_count = int(job.attempt_count or 0) + 1
        selected.append(job)
        if tenant_id is not None:
            per_tenant_counts[tenant_id] = per_tenant_counts.get(tenant_id, 0) + 1

    if candidates:
        db.commit()
    return selected


def mark_job_success(db: Session, job: JobQueue) -> None:
    job.status = "succeeded"
    job.finished_at = utcnow()
    job.locked_at = None
    job.locked_by = None
    job.last_error = None
    db.commit()


def reschedule_job(db: Session, job: JobQueue, *, error_message: str) -> None:
    policy = _policy_for_job(job)
    max_attempts = job.max_attempts or policy.max_attempts
    attempts = int(job.attempt_count or 0)
    if attempts >= max_attempts:
        move_to_dead_letter(db, job, error_message=error_message)
        return
    delay = _backoff_seconds(policy, attempts)
    job.status = "queued"
    job.run_at = utcnow() + timedelta(seconds=delay)
    job.locked_at = None
    job.locked_by = None
    job.last_error = error_message
    db.commit()
    record_queue_retry(job.queue_name, job.job_type)


def move_to_dead_letter(db: Session, job: JobQueue, *, error_message: str) -> None:
    dead = JobDeadLetter(
        original_job_id=job.id,
        queue_name=job.queue_name,
        job_type=job.job_type,
        tenant_id=job.tenant_id,
        payload_json=job.payload_json,
        attempt_count=job.attempt_count or 0,
        last_error=error_message,
        last_attempt_at=_normalize_dt(job.last_attempt_at),
        failed_at=utcnow(),
    )
    db.add(dead)
    db.delete(job)
    db.commit()


def queue_depth(db: Session, queue_name: str) -> int:
    return (
        db.query(JobQueue)
        .filter(JobQueue.queue_name == queue_name, JobQueue.status == "queued")
        .count()
    )
