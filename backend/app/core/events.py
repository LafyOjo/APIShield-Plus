# This file is a small utility layer for recording events into
# the database. The key idea is: not all actions are worth
# saving, only the “major” ones. This keeps the logs readable
# and focused on security-relevant moments.

from sqlalchemy.orm import Session
from app.crud.events import create_event

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
def log_event(db: Session, username: str | None, action: str, success: bool) -> None:
    #Persist an event if it is considered major.
    if action not in MAJOR_EVENTS:
        return
    create_event(db, username, action, success)
