# This file is a small utility layer for recording events into
# the database. The key idea is: not all actions are worth
# saving, only the “major” ones. This keeps the logs readable
# and focused on security-relevant moments.

import logging
from sqlalchemy.orm import Session

from app.core.request_meta import resolve_request_meta
from app.crud.events import create_event

logger = logging.getLogger(__name__)

# Define the small whitelist of actions that matter enough to
# persist. If a caller logs something outside this set, we’ll
# just skip it quietly. That way, our DB isn’t flooded with
# noise from trivial events.
MAJOR_EVENTS = {
    "login",
    "logout",
    "stuffing_attempt",
    "shop_login_error",
    "stuffing_block",
}

# This helper takes a DB session, a username, an action string,
# and whether it succeeded. If the action is in our whitelist,
# we forward it to create_event() so it’s written to the DB.
# Otherwise, we silently drop it.
def log_event(
    db: Session,
    tenant_id: int | None,
    username: str | None,
    action: str,
    success: bool,
    *,
    request=None,
    request_meta: dict[str, str | None] | None = None,
) -> None:
    # Persist an event only when tenant context is available.
    if action not in MAJOR_EVENTS or tenant_id is None:
        return
    meta = resolve_request_meta(request=request, request_meta=request_meta)
    client_ip = meta.get("client_ip") if meta else None
    user_agent = meta.get("user_agent") if meta else None
    request_path = meta.get("path") if meta else None
    referrer = meta.get("referer") if meta else None
    create_event(
        db,
        tenant_id,
        username,
        action,
        success,
        client_ip=client_ip,
        user_agent=user_agent,
        request_path=request_path,
        referrer=referrer,
    )
    if meta:
        logger.debug(
            "event.logged",
            extra={
                "tenant_id": tenant_id,
                "username": username,
                "action": action,
                "success": success,
                "request_id": meta.get("request_id"),
                "client_ip": meta.get("client_ip"),
            },
        )
