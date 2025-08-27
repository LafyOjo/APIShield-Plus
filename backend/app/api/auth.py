# This is the main authentication layer of the app.
# Responsibilities here:
#   - Register new users (with optional DemoShop sync)
#   - Handle login attempts with rate-limiting + policies
#   - Issue JWT tokens for API use
#   - Provide an authenticated "who am I" endpoint (/api/me)
#   - Logout + token revocation support
# The design is deliberately flexible so the same endpoints
# can work both standalone and when connected to DemoShop.

from datetime import timedelta
import os
import requests

from app.core.config import settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import (
    verify_password,
    create_access_token,
    get_password_hash,
)
from app.api.dependencies import get_current_user
from app.api.dependencies import oauth2_scheme
from app.core.security import revoke_token
from app.core.db import get_db
from app.crud.users import get_user_by_username, create_user
from app.crud.policies import get_policy_for_user
from app.core.events import log_event
from app.schemas.users import UserCreate, UserRead
from app.api.score import record_attempt, is_rate_limited, DEFAULT_FAIL_LIMIT


# Router setup — all routes here grouped under "auth"
router = APIRouter(tags=["auth"])


# Creates a new user in the local DB. Also, if DEMOSHOP syncing
# is enabled, it mirrors the registration into the Sock Shop demo.
# This is useful for showing how the auth system integrates with
# external services (but it’s optional and best-effort).
@router.post("/register", response_model=UserRead)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_username(db, user_in.username):
        raise HTTPException(status_code=400, detail="Username already registered")

    # Hash the password before storing (never store plaintext!)
    hashed = get_password_hash(user_in.password)
    role = user_in.role or "user"
    user = create_user(db, username=user_in.username, password_hash=hashed, role=role)

    # Optional: sync with DemoShop if env var is enabled
    if os.getenv("REGISTER_WITH_DEMOSHOP", "false").lower() in {"1", "true", "yes"}:
        shop_url = os.getenv("DEMO_SHOP_URL", "http://localhost:3005").rstrip("/")
        try:
            requests.post(
                f"{shop_url}/register",
                json={"username": user_in.username, "password": user_in.password},
                timeout=3,
            )
        except Exception:
            # Silent fail — we don’t want DemoShop errors to break core auth
            pass

    return user



# Traditional username/password login. Here’s what happens:
#   1. Look up user in DB, check their assigned security policy.
#   2. Enforce rate limiting based on failed attempts.
#   3. Verify credentials with hashed password check.
#   4. If successful → issue JWT + log the event.
#   5. Also mirrors login to DemoShop if enabled.
@router.post("/login")
def login(user_in: UserCreate, request: Request, db: Session = Depends(get_db)):
    user = get_user_by_username(db, user_in.username)
    policy = get_policy_for_user(db, user) if user else None
    fail_limit = policy.failed_attempts_limit if policy else DEFAULT_FAIL_LIMIT

    # Enforce account lockout/rate limiting
    if user and is_rate_limited(db, user.id, fail_limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail="Too many attempts"
        )

    # Verify credentials
    if not user or not verify_password(user_in.password, user.password_hash):
        log_event(db, user_in.username, "login", False)
        record_attempt(
            db,
            request.client.host,
            False,
            user_id=user.id if user else None,
            fail_limit=fail_limit,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Success path → issue token
    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    log_event(db, user.username, "login", True)
    record_attempt(
        db,
        request.client.host,
        True,
        user_id=user.id,
        fail_limit=fail_limit,
    )

    # Optional: mirror login into DemoShop
    if os.getenv("LOGIN_WITH_DEMOSHOP", "false").lower() in {"1", "true", "yes"}:
        shop_url = os.getenv("DEMO_SHOP_URL", "http://localhost:3005").rstrip("/")
        try:
            requests.post(
                f"{shop_url}/login",
                json={"username": user_in.username, "password": user_in.password},
                timeout=3,
            )
        except Exception:
            # Don’t break auth if DemoShop is down — just log it
            log_event(db, user.username, "shop_login_error", False)

    return {"access_token": token, "token_type": "bearer"}


# OAuth2-compatible login flow. This is what standard clients
# (like Swagger UI or external apps) will use. It works the same
# as /login but consumes form data and returns a bearer token.
@router.post("/api/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        log_event(db, form_data.username, "token", False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    log_event(db, user.username, "token", True)
    return {"access_token": access_token, "token_type": "bearer"}


# Returns info about the current user (from JWT).
# NOTE: We deliberately include password_hash in the response
# because the credential stuffing simulator relies on it.
# In production, you’d *never* expose hashes like this.
@router.get("/api/me")
async def read_me(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "password_hash": current_user.password_hash,
        "role": current_user.role,
    }


# Logs the user out by revoking their token.
# Even though JWTs are usually stateless, we implement a revoke
# list here so we can invalidate tokens before expiry (important
# for demos where we show active session control).
@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    success = False
    try:
        revoke_token(token)
        success = True
    except Exception:
        # If revoke fails, don’t crash — just mark unsuccessful
        pass
    log_event(db, current_user.username, "logout", success)
    return {"detail": "Logged out"}
