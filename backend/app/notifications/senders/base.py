from __future__ import annotations

from typing import Any

from app.models.notification_channels import NotificationChannel


class NotificationSender:
    def send(
        self,
        *,
        channel: NotificationChannel,
        payload: dict[str, Any],
        event_type: str,
        config_public: dict[str, Any],
        config_secret: dict[str, Any],
    ) -> None:
        raise NotImplementedError
