from __future__ import annotations

import argparse

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.onboarding_emails import run_no_events_nudge_job


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Queue onboarding email nudges.")
    parser.add_argument(
        "--threshold-hours",
        type=int,
        default=settings.ONBOARDING_NO_EVENTS_HOURS,
        help="Hours since signup to nudge.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        run_no_events_nudge_job(db, threshold_hours=args.threshold_hours)


if __name__ == "__main__":
    main()
