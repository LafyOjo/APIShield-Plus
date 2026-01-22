from __future__ import annotations

import argparse
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.metrics import record_job_run
from app.core.time import utcnow
from app.core.tracing import trace_span
from app.insights.interpretation import interpret_incident_record
from app.insights.incident_status import evaluate_status_transition
from app.insights.prescriptions import generate_prescriptions
from app.models.incidents import Incident
from app.models.revenue_impact import ImpactEstimate


logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_ITEMS = 200


def _needs_refresh(db: Session, incident: Incident) -> bool:
    if incident.impact_estimate_id is None:
        return True
    impact = (
        db.query(ImpactEstimate)
        .filter(
            ImpactEstimate.id == incident.impact_estimate_id,
            ImpactEstimate.tenant_id == incident.tenant_id,
        )
        .first()
    )
    if impact is None:
        return True
    if incident.last_seen_at and impact.window_end and impact.window_end < incident.last_seen_at:
        return True
    return False


def run_interpret_open_incidents(
    db: Session,
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    max_items: int = DEFAULT_MAX_ITEMS,
    force: bool = False,
) -> int:
    since = utcnow() - timedelta(hours=max(1, lookback_hours))
    candidates = (
        db.query(Incident)
        .filter(
            Incident.last_seen_at >= since,
            Incident.status != "resolved",
        )
        .order_by(Incident.last_seen_at.desc())
        .limit(max_items)
        .all()
    )
    updated = 0
    for incident in candidates:
        needs_impact = force or _needs_refresh(db, incident)
        needs_bundle = force or incident.prescription_bundle_id is None
        if not needs_impact and not needs_bundle:
            continue
        impact = None
        if needs_impact:
            impact = interpret_incident_record(db, incident=incident)
        bundle = None
        if needs_bundle or needs_impact:
            bundle = generate_prescriptions(db, incident=incident, impact_estimate=impact)
        new_status = evaluate_status_transition(db, incident, impact=impact)
        if new_status and new_status != incident.status:
            incident.status = new_status
            incident.status_manual = False
        if impact is not None or bundle is not None or new_status:
            updated += 1
    if updated:
        db.commit()
    return updated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interpret open incidents for conversion impact.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single interpretation pass and exit.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help="How far back to scan incidents.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help="Maximum number of incidents to interpret per run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute impact estimates even if already present.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    updated = 0
    success = True
    try:
        with SessionLocal() as db:
            with trace_span(
                "job.interpret_open_incidents",
                lookback_hours=args.lookback_hours,
                max_items=args.max_items,
            ):
                updated = run_interpret_open_incidents(
                    db,
                    lookback_hours=args.lookback_hours,
                    max_items=args.max_items,
                    force=args.force,
                )
        logger.info("Incident interpretation run complete. updated=%s", updated)
    except Exception:
        success = False
        logger.exception("Incident interpretation job failed")
        raise
    finally:
        record_job_run(job_name="interpret_open_incidents", success=success)
    if args.once:
        return


if __name__ == "__main__":
    main()
