# This file defines an API route that shows the last login
# timestamp for each user. It queries the database, grabs the
# most recent login times, and returns them in JSON format.
#
# The result is a simple dictionary: { "username": "timestamp" }
# where the timestamp is ISO 8601 (so the frontend can parse it).

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.api.dependencies import get_current_user
from app.crud.events import get_last_logins
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.tenancy.dependencies import require_tenant_context

# Prefix ensures everything here lives under /api/last-logins
router = APIRouter(prefix="/last-logins", tags=["stats"])


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


# GET /api/last-logins/
#
# Requires authentication. Pulls last login times from the DB
# using our CRUD helper and converts them into ISO8601 strings.
# This keeps the API consistent and makes parsing easier for 
# the React frontend and any external tools.
@router.get("/")
def read_last_logins(
    db: Session = Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    data = get_last_logins(db, tenant_id)
    # convert Python datetime objects into ISO strings for JSON
    return {u: ts.isoformat() for u, ts in data.items()}
