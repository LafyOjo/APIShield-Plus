from __future__ import annotations

import argparse
import logging
from datetime import timezone
from time import monotonic, sleep
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import (
    record_queue_depth,
    record_queue_job,
    record_queue_runtime,
    record_queue_wait,
)
from app.core.queue import (
    claim_jobs,
    get_job_handler,
    register_job_handler,
    reschedule_job,
    mark_job_success,
    queue_depth,
)
from app.core.time import utcnow
from app.jobs.data_exports import run_data_exports
from app.jobs.geo_enrich import run_geo_enrichment
from app.jobs.interpret_open_incidents import run_interpret_open_incidents
from app.jobs.marketplace_seed import run_marketplace_seed
from app.jobs.notification_sender import run_notification_sender
from app.jobs.revenue_leak import run_revenue_leak_job
from app.jobs.trust_scoring import run_trust_scoring
from app.core.db import SessionLocal


logger = logging.getLogger(__name__)


def _handle_notifications(db: Session, payload: dict) -> int:
    return run_notification_sender(
        db,
        batch_size=int(payload.get("batch_size", 100)),
    )


def _handle_incident_updates(db: Session, payload: dict) -> int:
    return run_interpret_open_incidents(
        db,
        lookback_hours=int(payload.get("lookback_hours", 24)),
        max_items=int(payload.get("max_items", 200)),
        force=bool(payload.get("force", False)),
    )


def _handle_trust_scoring(db: Session, payload: dict) -> int:
    return run_trust_scoring(
        db,
        lookback_hours=int(payload.get("lookback_hours", 24)),
        recompute_hours=int(payload.get("recompute_hours", 2)),
    )


def _handle_revenue_leak(db: Session, payload: dict) -> int:
    return run_revenue_leak_job(
        db,
        lookback_hours=int(payload.get("lookback_hours", 24)),
        recompute_hours=int(payload.get("recompute_hours", 2)),
    )


def _handle_geo_enrich(db: Session, payload: dict) -> int:
    return run_geo_enrichment(
        db,
        lookback_minutes=int(payload.get("lookback_minutes", 15)),
        max_items=int(payload.get("max_items", 1000)),
    )


def _handle_data_exports(db: Session, payload: dict) -> int:
    return run_data_exports(
        db,
        max_configs=int(payload.get("max_configs", 50)),
    )


def _handle_marketplace_seed(db: Session, _payload: dict) -> int:
    return run_marketplace_seed(db)


def register_default_handlers() -> None:
    register_job_handler("notification_send", _handle_notifications)
    register_job_handler("incident_update", _handle_incident_updates)
    register_job_handler("trust_scoring", _handle_trust_scoring)
    register_job_handler("revenue_leak", _handle_revenue_leak)
    register_job_handler("geo_enrich", _handle_geo_enrich)
    register_job_handler("data_exports", _handle_data_exports)
    register_job_handler("marketplace_seed", _handle_marketplace_seed)


def _normalize_dt(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def run_queue_once(
    db: Session,
    *,
    queue_name: str,
    worker_id: str,
    limit: int = 10,
) -> int:
    depth = queue_depth(db, queue_name)
    record_queue_depth(queue_name, depth)
    jobs = claim_jobs(db, queue_name=queue_name, limit=limit, worker_id=worker_id)
    if not jobs:
        return 0
    processed = 0
    for job in jobs:
        wait_seconds = None
        created_at = _normalize_dt(job.created_at)
        now = _normalize_dt(utcnow())
        if created_at:
            wait_seconds = max(0.0, (now - created_at).total_seconds())
        if wait_seconds is not None:
            record_queue_wait(queue_name, job.job_type, wait_seconds)

        start = monotonic()
        handler = get_job_handler(job.job_type)
        if handler is None:
            error_message = "no_handler_registered"
            reschedule_job(db, job, error_message=error_message)
            record_queue_job(queue_name, job.job_type, status="failed")
            processed += 1
            continue

        try:
            handler(db, job.payload_json or {})
        except Exception as exc:
            logger.exception("Queue job failed: %s", exc)
            reschedule_job(db, job, error_message=str(exc))
            record_queue_job(queue_name, job.job_type, status="failed")
            processed += 1
            continue

        mark_job_success(db, job)
        record_queue_job(queue_name, job.job_type, status="success")
        runtime = monotonic() - start
        record_queue_runtime(queue_name, job.job_type, runtime)
        processed += 1
    return processed


def run_queue_group_once(
    db: Session,
    *,
    queue_names: Iterable[str],
    worker_id: str,
    limit: int,
) -> int:
    total = 0
    for queue_name in queue_names:
        total += run_queue_once(
            db,
            queue_name=queue_name,
            worker_id=worker_id,
            limit=limit,
        )
    return total


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queue worker.")
    parser.add_argument(
        "--queue",
        choices=["critical", "standard", "bulk", "all"],
        default="standard",
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=None)
    parser.add_argument("--worker-id", type=str, default="worker-1")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    poll_interval = (
        float(args.poll_interval)
        if args.poll_interval is not None
        else float(settings.JOB_QUEUE_POLL_INTERVAL_SECONDS)
    )
    register_default_handlers()
    queue_names = ["critical", "standard", "bulk"] if args.queue == "all" else [args.queue]

    while True:
        processed = 0
        with SessionLocal() as db:
            processed = run_queue_group_once(
                db,
                queue_names=queue_names,
                worker_id=args.worker_id,
                limit=args.limit,
            )
        if args.once:
            break
        if processed == 0:
            sleep(max(0.1, poll_interval))


if __name__ == "__main__":
    main()
