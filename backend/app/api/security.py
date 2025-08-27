
# This module centralizes two related ideas: (1) a global on/off flag
# that lets us simulate “defenses enabled vs disabled,” and (2) a simple
# rotating “chain token” mechanism that forces each protected request to
# present the current token value, which rotates after every valid use.
# It’s intentionally lightweight so demos can illustrate the concepts
# without dragging in heavyweight, external dependencies.

from fastapi import APIRouter, HTTPException, Depends
import hashlib
import secrets

from app.core.config import settings
from app.api.dependencies import require_role

# ------------------------------------------------------------
# SECURITY_ENABLED is a single switch that controls whether the
# stuffing protections are enforced. In demos, being able to flip
# this at runtime is super helpful: you can show the exact same flow
# with defenses off (attacks succeed) and on (attacks blocked),
# all without restarting the app or changing code paths.
SECURITY_ENABLED = True

# ------------------------------------------------------------
# CURRENT_CHAIN stores the “one-time” chain value expected from
# the next protected request. Think of it like a running secret:
# clients must present the current token, and on success we rotate
# it forward. That rotation makes replayed or stale requests easy
# to detect and reject on the spot.
CURRENT_CHAIN = None


# ------------------------------------------------------------
# _hash(value) is a tiny helper that wraps SHA-256 for readability.
# Using a fixed, strong hash keeps the chain derivation simple while
# still being deterministic and tamper-evident. The seed input mixes
# in a secret so raw token material is never stored or compared.
def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ------------------------------------------------------------
# _new_chain(prev) derives the next chain value. We combine either
# the previous chain (if present) or a stable app secret with some
# fresh randomness. That gives us forward movement + unpredictability,
# so each call gets a new token and replay defense comes for free.
def _new_chain(prev: str | None = None) -> str:
    """Return a new chain value derived from ``prev`` and randomness."""
    seed = prev or settings.SECRET_KEY
    return _hash(seed + secrets.token_hex(8))


# ------------------------------------------------------------
# init_chain() is called at startup (and when security flips on)
# so the first request has a valid chain to present. I keep it
# tiny and explicit to avoid any “None” surprises, and so that
# the rotation logic stays straightforward across the lifetime.
def init_chain() -> None:
    """Initialise the global chain value."""
    global CURRENT_CHAIN
    CURRENT_CHAIN = _new_chain()


# ------------------------------------------------------------
# rotate_chain() advances the chain state after a successful check.
# Rotating ensures the same token can’t be used twice, which gives
# us a clean, easy replay-protection story even without timestamps
# or complex server-side state machines. One in, one out—done.
def rotate_chain() -> None:
    """Advance the chain to the next value."""
    global CURRENT_CHAIN
    CURRENT_CHAIN = _new_chain(CURRENT_CHAIN)


# ------------------------------------------------------------
# verify_chain(token) is the gatekeeper. It compares the presented
# token to the expected CURRENT_CHAIN. If they don’t match, we reject
# with a 401 and never rotate. If they do match, we rotate immediately
# so the token cannot be replayed. Simple, fast, and state-light.
def verify_chain(token: str | None) -> None:
    """Validate ``token`` matches the current chain and rotate."""
    if token != CURRENT_CHAIN:
        raise HTTPException(status_code=401, detail="Invalid chain token")
    rotate_chain()


# ------------------------------------------------------------
# Initialize the chain as soon as this module is imported, which
# happens when the app starts. That way, protected routes that check
# the chain have a valid initial value without any explicit boot step.
# Re-initialization also happens when SECURITY_ENABLED flips to True.
init_chain()

# ------------------------------------------------------------
# Router configuration: all endpoints live under /api/security
# and get tagged as “security” in the docs. Keeping these controls
# in a dedicated router makes them easy to find and to lock behind
# admin-only authorization requirements.
router = APIRouter(prefix="/api/security", tags=["security"])


# ------------------------------------------------------------
# GET /api/security/
# Returns the current “defenses on/off” state. I lock this behind
# an admin role because even read access can leak implementation
# details. The payload is intentionally small: a single boolean
# that the UI can turn into a neat toggle.
@router.get("/")
def get_security(_user=Depends(require_role("admin"))):
    """Return current security enforcement state."""
    return {"enabled": SECURITY_ENABLED}


# ------------------------------------------------------------
# GET /api/security/chain
# Exposes the current chain value to admins only. In the demo flow,
# the test client or simulator fetches this and then presents it in
# the X-Chain-Password header. Because we rotate on every successful
# verification, this value changes after each valid protected call.
@router.get("/chain")
def get_chain(_user=Depends(require_role("admin"))):
    """Retrieve the current chain value."""
    return {"chain": CURRENT_CHAIN}


# ------------------------------------------------------------
# POST /api/security/
# Allows an admin to toggle SECURITY_ENABLED at runtime. When enabling,
# we also re-initialize the chain so a fresh, unpredictable value kicks
# off the next cycle. When disabling, we clear the chain so no one can
# accidentally rely on it while protections are off.
@router.post("/")
def set_security(payload: dict, _user=Depends(require_role("admin"))):
    """Update security enforcement state."""
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="'enabled' boolean required")
    global SECURITY_ENABLED
    SECURITY_ENABLED = enabled
    if enabled:
        init_chain()
    else:
        # Clear chain when security disabled to avoid stale expectations.
        global CURRENT_CHAIN
        CURRENT_CHAIN = None
    return {"enabled": SECURITY_ENABLED}
