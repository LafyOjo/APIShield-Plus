from __future__ import annotations

import argparse
import logging
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.core.db import SessionLocal
from app.core.metrics import record_job_run, record_notification_delivery
from app.core.time import utcnow
from app.core.tracing import trace_span
from app.models.notification_channels import NotificationChannel
from app.models.notification_deliveries import NotificationDelivery
from app.models.notification_rules import NotificationRule
from app.notifications.senders import get_sender


logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_SECONDS = 60


def _can_attempt(delivery: NotificationDelivery, now, base_backoff_seconds: int) -> bool:
    if delivery.attempt_count <= 0:
        return True
    created_at = delivery.created_at
    if created_at.tzinfo is None and getattr(now, "tzinfo", None) is not None:
        now = now.replace(tzinfo=None)
    elif created_at.tzinfo is not None and getattr(now, "tzinfo", None) is None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    delay = base_backoff_seconds * (2 ** max(delivery.attempt_count - 1, 0))
    next_allowed = created_at + timedelta(seconds=delay)
    return now >= next_allowed


def run_notification_sender(
    db: Session,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
) -> int:
    now = utcnow()
    deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.status == "queued")
        .order_by(NotificationDelivery.created_at.asc())
        .limit(batch_size)
        .all()
    )
    processed = 0
    for delivery in deliveries:
        if delivery.attempt_count >= max_attempts:
            delivery.status = "failed"
            delivery.error_message = "max_attempts_exceeded"
            processed += 1
            continue
        if not _can_attempt(delivery, now, base_backoff_seconds):
            continue

        rule = (
            db.query(NotificationRule)
            .filter(NotificationRule.id == delivery.rule_id)
            .first()
        )
        if not rule or not rule.is_enabled:
            delivery.status = "skipped"
            delivery.error_message = "rule_disabled"
            processed += 1
            continue

        channel = (
            db.query(NotificationChannel)
            .filter(NotificationChannel.id == delivery.channel_id)
            .first()
        )
        if not channel or not channel.is_enabled:
            delivery.status = "skipped"
            delivery.error_message = "channel_disabled"
            processed += 1
            continue

        sender = get_sender(channel.type)
        if sender is None:
            delivery.status = "failed"
            delivery.error_message = "unsupported_channel_type"
            processed += 1
            continue

        config_public = channel.config_public_json if isinstance(channel.config_public_json, dict) else {}
        config_secret = {}
        if channel.config_secret_enc:
            try:
                config_secret = decrypt_json(channel.config_secret_enc)
            except Exception as exc:
                delivery.status = "failed"
                delivery.error_message = str(exc)
                channel.last_error = str(exc)
                channel.last_tested_at = now
                processed += 1
                continue

        delivery.attempt_count += 1
        channel.last_tested_at = now
        try:
            with trace_span(
                "notification.send",
                tenant_id=delivery.tenant_id,
                channel_id=delivery.channel_id,
                channel_type=channel.type,
                trigger_type=rule.trigger_type,
            ):
                sender.send(
                    channel=channel,
                    payload=delivery.payload_json,
                    event_type=rule.trigger_type,
                    config_public=config_public,
                    config_secret=config_secret,
                )
        except Exception as exc:
            delivery.error_message = str(exc)
            channel.last_error = str(exc)
            record_notification_delivery(
                channel_type=channel.type,
                trigger_type=rule.trigger_type,
                success=False,
            )
            if delivery.attempt_count >= max_attempts:
                delivery.status = "failed"
            processed += 1
            continue

        delivery.status = "sent"
        delivery.sent_at = now
        delivery.error_message = None
        channel.last_error = None
        record_notification_delivery(
            channel_type=channel.type,
            trigger_type=rule.trigger_type,
            success=True,
        )
        processed += 1

    if processed:
        db.commit()
    return processed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send queued notification deliveries.")
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--backoff-seconds", type=int, default=DEFAULT_BACKOFF_SECONDS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    processed = 0
    success = True
    try:
        with SessionLocal() as db:
            processed = run_notification_sender(
                db,
                batch_size=args.batch_size,
                max_attempts=args.max_attempts,
                base_backoff_seconds=args.backoff_seconds,
            )
        logger.info("Notification sender run complete. processed=%s", processed)
    except Exception:
        success = False
        logger.exception("Notification sender failed")
        raise
    finally:
        record_job_run(job_name="notification_sender", success=success)
    if args.once:
        return


if __name__ == "__main__":
    main()
