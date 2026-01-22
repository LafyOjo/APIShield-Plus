from __future__ import annotations

import logging
from typing import Any

from app.models.notification_channels import NotificationChannel
from app.notifications.senders.base import NotificationSender


logger = logging.getLogger(__name__)


class EmailSender(NotificationSender):
    def send(
        self,
        *,
        channel: NotificationChannel,
        payload: dict[str, Any],
        event_type: str,
        config_public: dict[str, Any],
        config_secret: dict[str, Any],
    ) -> None:
        _ = config_secret
        recipients = config_public.get("recipients") if isinstance(config_public, dict) else None
        logger.info(
            "Email stub: event_type=%s channel_id=%s recipients=%s payload=%s",
            event_type,
            channel.id,
            recipients,
            payload,
        )
