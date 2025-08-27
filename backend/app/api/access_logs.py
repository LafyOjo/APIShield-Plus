# 
# Access Logs API Router
# 
# This module exposes a tiny, focused API for reading access logs.
# It’s intentionally minimal: one endpoint, a couple of filters,
# and a simple authorization check that restricts visibility based
# on the caller’s role. Admins can see everything; users see only theirs.
# Keeping this separate makes logs easy to wire into any app surface.

from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Core application dependencies: database session factory and CRUD.
# I keep DB access behind get_db() so each request gets a clean session,
# and I centralize log retrieval in the CRUD layer so business rules
# stay out of the router. That separation keeps HTTP glue code simple.
from app.core.db import get_db
from app.crud.access_logs import get_access_logs

# Pydantic response schema for serialization.
# Returning concrete types (AccessLogRead) means the shape is predictable,
# and FastAPI can auto-document the contract. That’s handy for clients
# and protects us from accidentally leaking internal fields on the model.
from app.schemas.access_logs import AccessLogRead

# Authentication/authorization dependency. The router doesn’t care
# how the user is verified; it just needs a current_user object with
# role/username attributes. This makes swapping auth providers painless.
from app.api.dependencies import get_current_user

# Create a dedicated router for access logs with a clean prefix and tag.
# Prefix means all routes under here start with /api/access-logs,
# and tagging lets docs group these endpoints together automatically.
router = APIRouter(prefix="/api/access-logs", tags=["logs"])


@router.get("/", response_model=List[AccessLogRead])
def read_access_logs(

    # Optional query parameters to filter what we fetch.
    # 'username' scops logs to a specific user; 'hours' limits the time window.
    # Both are nullable so the endpoint can serve “all recent logs” if empty.
    username: Optional[str] = None,
    hours: Optional[int] = None,

    # Inject a database session for this request. Using Depends ensures
    # proper lifecycle management (open/close/rollback) and keeps this
    # function fully testable—pass a session and it just works.
    db: Session = Depends(get_db),

    # Current user comes from our auth dependency. We rely on a simple
    # contract: the object exposes 'role' and 'username'. That’s all we need
    # to enforce the “admin sees all, users see self” rule below.
    current_user=Depends(get_current_user),
):
    # Authorization rule in one sentence: if you are not an admin, you can
    # only read your own logs. We enforce that by overriding the username
    # filter when the caller’s role is anything other than "admin". This
    # avoids complex policy code and prevents horizontal data exposure.
    if getattr(current_user, "role", None) != "admin":
        username = getattr(current_user, "username", None)

    # Hand off to the CRUD layer with the final filters. The CRUD function
    # knows how to shape the database query and return results in model form.
    # The response_model annotation on the route handles serialization to JSON,
    # so the client receives a tidy, predictable array of AccessLogRead objects.
    return get_access_logs(db, username=username, hours=hours)
