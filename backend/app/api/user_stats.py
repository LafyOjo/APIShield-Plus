# This file adds a very focused endpoint: exposing per-user API
# call counts to admins. It’s part of the “stats” tag family,
# meaning the dashboard can pull these numbers for reporting or
# anomaly detection. Since it’s security-sensitive, only admins
# can reach it, and the router lives under /api/user-calls.
# ------------------------------------------------------------

from fastapi import APIRouter, Depends

from app.core.metrics import get_user_counts
from app.api.dependencies import require_role

# ------------------------------------------------------------
# We mount the router at /api/user-calls and tag it as “stats”.
# That means in the OpenAPI docs, it shows up in the “stats”
# section and every endpoint here is prefixed accordingly.
router = APIRouter(prefix="/api/user-calls", tags=["stats"])


#
# This route is locked down to admins (via require_role).
# It returns a simple dictionary keyed by username, where the
# value is the total number of API calls seen. The numbers
# come straight from our metrics helper, which maintains counts
# during normal request processing.
# ------------------------------------------------------------
@router.get("/", dependencies=[Depends(require_role("admin"))])
def read_user_calls():
    """Return total API call counts per user."""
    return get_user_counts()
