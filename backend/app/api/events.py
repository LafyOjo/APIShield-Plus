# This router exposes endpoints for reading system events.
# Events are things like logins, alerts, or other activity 
# tracked in the DB so that the dashboard can visualize 
# what’s happening in real-time or historically.
#
# The routes here are protected by authentication, so only
# logged-in users can request events. We also optionally 
# filter by time (last X hours).

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.crud.events import get_events
from app.schemas.events import EventRead
from app.api.dependencies import get_current_user
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.tenancy.dependencies import require_tenant_context

# All event-related endpoints live under /api/events
router = APIRouter(prefix="/events", tags=["events"])

def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id

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
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_events(db, tenant_id, hours)
