from datetime import datetime, timezone, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.email_queue import EmailQueue


def get_latest_email(
    db: Session,
    *,
    tenant_id: int | None,
    user_id: int | None,
    dedupe_key: str,
) -> EmailQueue | None:
    return (
        db.query(EmailQueue)
        .filter(
            EmailQueue.tenant_id == tenant_id,
            EmailQueue.user_id == user_id,
            EmailQueue.dedupe_key == dedupe_key,
        )
        .order_by(EmailQueue.created_at.desc())
        .first()
    )


def recently_queued(
    db: Session,
    *,
    tenant_id: int | None,
    user_id: int | None,
    dedupe_key: str,
    cooldown_hours: int | None = None,
) -> bool:
    if cooldown_hours is None or cooldown_hours <= 0:
        return False
    latest = get_latest_email(db, tenant_id=tenant_id, user_id=user_id, dedupe_key=dedupe_key)
    if not latest or not latest.created_at:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
    created_at = latest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at >= cutoff


def create_email_queue(
    db: Session,
    *,
    tenant_id: int | None,
    user_id: int | None,
    to_email: str,
    template_key: str,
    dedupe_key: str,
    subject: str,
    body: str,
    trigger_event: str | None = None,
    metadata: dict | None = None,
) -> EmailQueue | None:
    record = EmailQueue(
        tenant_id=tenant_id,
        user_id=user_id,
        to_email=to_email,
        template_key=template_key,
        dedupe_key=dedupe_key,
        trigger_event=trigger_event,
        subject=subject,
        body=body,
        status="queued",
        metadata_json=metadata or None,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(record)
    return record
