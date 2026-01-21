from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.insights.incident_status import evaluate_status_transition
from app.insights.recovery import DEFAULT_POST_WINDOW_HOURS, compute_recovery
from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionItem


logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_MAX_ITEMS = 200


def run_recovery_measurement(
    db: Session,
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    max_items: int = DEFAULT_MAX_ITEMS,
    window_hours: int = DEFAULT_POST_WINDOW_HOURS,
    threshold: float | None = None,
    force: bool = False,
) -> int:
    since = datetime.utcnow() - timedelta(hours=max(1, int(lookback_hours or 0)))

    applied_subq = (
        db.query(
            PrescriptionItem.incident_id.label("incident_id"),
            func.min(PrescriptionItem.applied_at).label("first_applied_at"),
        )
        .filter(
            PrescriptionItem.status == "applied",
            PrescriptionItem.applied_at.isnot(None),
        )
        .group_by(PrescriptionItem.incident_id)
        .subquery()
    )

    candidates = (
        db.query(Incident)
        .join(applied_subq, Incident.id == applied_subq.c.incident_id)
        .filter(
            Incident.impact_estimate_id.isnot(None),
            applied_subq.c.first_applied_at >= since,
        )
        .order_by(applied_subq.c.first_applied_at.asc())
        .limit(max_items)
        .all()
    )

    updated = 0
    for incident in candidates:
        try:
            result = compute_recovery(
                db,
                incident.id,
                window_hours=window_hours,
                force=force,
            )
            if result:
                new_status = evaluate_status_transition(
                    db,
                    incident,
                    recovery=result["recovery"],
                    mitigation_recovery_ratio=threshold,
                )
                if new_status and new_status != incident.status:
                    incident.status = new_status
                    incident.status_manual = False
                db.commit()
                updated += 1
        except Exception:
            db.rollback()
            logger.exception("recovery measurement failed for incident %s", incident.id)
    return updated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure post-fix recovery for incidents.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single recovery pass and exit.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help="How far back to scan applied prescriptions.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help="Maximum number of incidents to evaluate per run.",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=DEFAULT_POST_WINDOW_HOURS,
        help="How many hours to measure after the first applied fix.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override recovery ratio threshold to mark incidents mitigated.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute recovery even if a matching measurement already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        updated = run_recovery_measurement(
            db,
            lookback_hours=args.lookback_hours,
            max_items=args.max_items,
            window_hours=args.window_hours,
            threshold=args.threshold,
            force=args.force,
        )
    logger.info("Recovery measurement run complete. updated=%s", updated)
    if args.once:
        return


if __name__ == "__main__":
    main()
