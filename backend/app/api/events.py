# This router exposes endpoints for reading system events.
# Events are things like logins, alerts, or other activity 
# tracked in the DB so that the dashboard can visualize 
# what’s happening in real-time or historically.
#
# The routes here are protected by authentication, so only
# logged-in users can request events. We also optionally 
# filter by time (last X hours).

from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.crud.events import get_events
from app.schemas.events import EventRead
from app.api.dependencies import get_current_user

# All event-related endpoints live under /api/events
router = APIRouter(prefix="/api/events", tags=["events"])

# GET /api/events
#
# Parameters:
#   - hours: if provided, only return events within the last N hours.
#
# Security:
#   - Requires a valid authenticated user (via get_current_user).
#
# This is what powers the "Events" table in the frontend.
@router.get("/", response_model=List[EventRead])
def read_events(
    hours: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return get_events(db, hours)
