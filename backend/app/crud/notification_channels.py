from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_json
from app.models.notification_channels import NotificationChannel


def create_channel(
    db: Session,
    *,
    tenant_id: int,
    channel_type: str,
    name: str,
    created_by_user_id: int | None = None,
    is_enabled: bool = True,
    config_public: dict[str, Any] | None = None,
    config_secret: dict[str, Any] | None = None,
    categories_allowed: list[str] | None = None,
) -> NotificationChannel:
    encrypted = None
    if config_secret is not None:
        encrypted = encrypt_json(config_secret)
    channel = NotificationChannel(
        tenant_id=tenant_id,
        type=channel_type,
        name=name,
        is_enabled=is_enabled,
        created_by_user_id=created_by_user_id,
        config_public_json=config_public,
        config_secret_enc=encrypted,
        categories_allowed=categories_allowed,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def list_channels(db: Session, tenant_id: int) -> list[NotificationChannel]:
    return (
        db.query(NotificationChannel)
        .filter(NotificationChannel.tenant_id == tenant_id)
        .order_by(NotificationChannel.id.desc())
        .all()
    )


def get_channel(
    db: Session,
    tenant_id: int,
    channel_id: int,
) -> NotificationChannel | None:
    return (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.tenant_id == tenant_id,
            NotificationChannel.id == channel_id,
        )
        .first()
    )


def update_channel(
    db: Session,
    tenant_id: int,
    channel_id: int,
    *,
    name: str | None = None,
    is_enabled: bool | None = None,
    config_public: dict[str, Any] | None = None,
    config_secret: dict[str, Any] | None = None,
    categories_allowed: list[str] | None = None,
    last_tested_at: datetime | None = None,
    last_error: str | None = None,
) -> NotificationChannel | None:
    channel = get_channel(db, tenant_id, channel_id)
    if not channel:
        return None
    if name is not None:
        channel.name = name
    if is_enabled is not None:
        channel.is_enabled = is_enabled
    if config_public is not None:
        channel.config_public_json = config_public
    if config_secret is not None:
        channel.config_secret_enc = encrypt_json(config_secret)
    if categories_allowed is not None:
        channel.categories_allowed = categories_allowed
    if last_tested_at is not None:
        channel.last_tested_at = last_tested_at
    if last_error is not None:
        channel.last_error = last_error
    db.commit()
    db.refresh(channel)
    return channel


def disable_channel(
    db: Session,
    tenant_id: int,
    channel_id: int,
) -> NotificationChannel | None:
    channel = get_channel(db, tenant_id, channel_id)
    if not channel:
        return None
    channel.is_enabled = False
    db.commit()
    db.refresh(channel)
    return channel
