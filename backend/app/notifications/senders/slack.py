from __future__ import annotations

from typing import Any

import requests

from app.models.notification_channels import NotificationChannel
from app.notifications.senders.base import NotificationSender


def _build_slack_text(payload: dict[str, Any]) -> str:
    if payload.get("type") == "incident":
        severity = str(payload.get("severity") or "").upper()
        title = payload.get("title") or "Incident"
        impact = payload.get("impact") or {}
        lost_revenue = impact.get("estimated_lost_revenue")
        if lost_revenue is not None:
            return f"[{severity}] {title} (est. lost revenue {lost_revenue})"
        return f"[{severity}] {title}"
    if payload.get("type") == "conversion_drop":
        metric = payload.get("metric_key") or "conversion metric"
        delta = payload.get("delta_percent")
        if delta is not None:
            return f"Conversion drop detected for {metric} ({delta:.1f}%)"
        return f"Conversion drop detected for {metric}"
    return payload.get("title") or "Security notification"


def _build_slack_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    text = _build_slack_text(payload)
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]
    links = payload.get("links") or {}
    link_lines = []
    if links.get("incident"):
        link_lines.append(f"*Incident:* {links['incident']}")
    if links.get("map"):
        link_lines.append(f"*Map:* {links['map']}")
    if links.get("events"):
        link_lines.append(f"*Events:* {links['events']}")
    if link_lines:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(link_lines)}}
        )
    return blocks


class SlackSender(NotificationSender):
    def send(
        self,
        *,
        channel: NotificationChannel,
        payload: dict[str, Any],
        event_type: str,
        config_public: dict[str, Any],
        config_secret: dict[str, Any],
    ) -> None:
        _ = event_type, config_public
        webhook_url = config_secret.get("webhook_url") or config_secret.get("url")
        if not webhook_url:
            raise ValueError("Slack webhook URL not configured")
        body = {
            "text": _build_slack_text(payload),
            "blocks": _build_slack_blocks(payload),
        }
        resp = requests.post(webhook_url, json=body, timeout=10)
        if resp.status_code >= 400:
            raise ValueError(f"Slack webhook failed with status {resp.status_code}")
