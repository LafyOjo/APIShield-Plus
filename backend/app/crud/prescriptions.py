from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.prescriptions import PrescriptionItem


ALLOWED_STATUSES = {"suggested", "applied", "dismissed", "snoozed"}
DEFAULT_SNOOZE_DAYS = 7


def can_transition(current: str, target: str) -> bool:
    if current == target:
        return True
    if current in {"applied", "dismissed"}:
        return False
    if current in {"suggested", "snoozed"}:
        return target in {"suggested", "applied", "dismissed", "snoozed"}
    return False


def update_prescription_item_status(
    db: Session,
    *,
    item: PrescriptionItem,
    status: str | None,
    notes: str | None = None,
    snoozed_until: datetime | None = None,
    applied_by_user_id: int | None = None,
) -> PrescriptionItem:
    if status is not None:
        normalized = status.strip().lower()
        if normalized not in ALLOWED_STATUSES:
            raise ValueError("Invalid status")
        if not can_transition(item.status, normalized):
            raise ValueError("Status transition not allowed")
        item.status = normalized

    if notes is not None:
        item.notes = notes

    if item.status == "applied":
        if item.applied_at is None:
            item.applied_at = datetime.utcnow()
        item.dismissed_at = None
        item.snoozed_until = None
        if applied_by_user_id:
            item.applied_by_user_id = applied_by_user_id
    elif item.status == "dismissed":
        if item.dismissed_at is None:
            item.dismissed_at = datetime.utcnow()
        item.applied_at = None
        item.snoozed_until = None
    elif item.status == "snoozed":
        if snoozed_until is None:
            snoozed_until = datetime.utcnow() + timedelta(days=DEFAULT_SNOOZE_DAYS)
        item.snoozed_until = snoozed_until
        item.applied_at = None
        item.dismissed_at = None
    elif item.status == "suggested":
        item.applied_at = None
        item.dismissed_at = None
        item.snoozed_until = None

    db.add(item)
    return item
