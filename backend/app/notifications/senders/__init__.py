from app.notifications.senders.base import NotificationSender
from app.notifications.senders.email import EmailSender
from app.notifications.senders.slack import SlackSender
from app.notifications.senders.webhook import WebhookSender


_SENDER_REGISTRY: dict[str, NotificationSender] = {
    "slack": SlackSender(),
    "webhook": WebhookSender(),
    "email": EmailSender(),
}


def get_sender(channel_type: str) -> NotificationSender | None:
    if not channel_type:
        return None
    return _SENDER_REGISTRY.get(str(channel_type).strip().lower())
