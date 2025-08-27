# This small API file exposes read-only configuration details
# to the frontend/dashboard. For now it only shares the 
# "fail_limit" setting (how many failed login attempts are
# allowed before rate limiting / lockout kicks in).
#
# Only admins can call this endpoint, to prevent regular users
# from learning security policy details like thresholds.

from fastapi import APIRouter, Depends
import os

from app.api.score import DEFAULT_FAIL_LIMIT
from app.api.dependencies import require_role

# Router setup — all endpoints here tagged as "config"
router = APIRouter(tags=["config"])


# Returns the currently active fail_limit value.
# This comes either from the FAIL_LIMIT environment variable
# (so it’s easy to override per deployment) or falls back to
# the code default.  The require_role("admin") dependency 
# ensures that only admins can query this setting.
@router.get("/config")
def get_config(_user=Depends(require_role("admin"))):
    """Return the current FAIL_LIMIT configuration value."""
    fail_limit = int(os.getenv("FAIL_LIMIT", DEFAULT_FAIL_LIMIT))
    return {"fail_limit": fail_limit}
