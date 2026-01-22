from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any

import requests

from app.models.notification_channels import NotificationChannel
from app.notifications.senders.base import NotificationSender


def _encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _sign_payload(secret: str, timestamp: str, body: str) -> str:
    message = f"{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class WebhookSender(NotificationSender):
    def send(
        self,
        *,
        channel: NotificationChannel,
        payload: dict[str, Any],
        event_type: str,
        config_public: dict[str, Any],
        config_secret: dict[str, Any],
    ) -> None:
        _ = channel, config_public
        url = config_secret.get("url") or config_secret.get("webhook_url")
        if not url:
            raise ValueError("Webhook URL not configured")
        secret = config_secret.get("signing_secret") or config_secret.get("secret")
        body_payload = {"event_type": event_type, "payload": payload}
        body = _encode_payload(body_payload)
        headers = {"Content-Type": "application/json"}
        timestamp = None
        if secret:
            timestamp = str(int(datetime.now(timezone.utc).timestamp()))
            signature = _sign_payload(secret, timestamp, body)
            headers["X-Timestamp"] = timestamp
            headers["X-Signature"] = signature
        resp = requests.post(url, data=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            raise ValueError(f"Webhook failed with status {resp.status_code}")
