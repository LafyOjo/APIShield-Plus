from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.oidc import (
    build_authorize_url,
    create_state_token,
    decode_state_token,
    exchange_code_for_tokens,
    fetch_discovery,
    generate_nonce,
    sanitize_next_path,
    verify_id_token,
)
from app.core.security import create_access_token, get_password_hash
from app.crud.memberships import create_membership
from app.crud.tenant_sso import decrypt_client_secret, get_sso_config
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.users import create_user, get_user_by_username
from app.crud.audit import create_audit_log
from app.models.enums import MembershipStatusEnum
from app.models.memberships import Membership
from app.schemas.sso import TenantSSOStatus
from app.api.auth import _membership_snapshot


router = APIRouter(prefix="/auth/oidc", tags=["sso"])


def _resolve_tenant(db: Session, tenant_hint: str | None):
    if not tenant_hint:
        return None
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    return tenant


def _email_domain_allowed(email: str, allowed_domains: list[str] | None) -> bool:
    if not allowed_domains:
        return True
    if "@" not in email:
        return False
    domain = email.split("@", 1)[1].strip().lower()
    return domain in {d.strip().lower() for d in allowed_domains if d}


@router.get("/status", response_model=TenantSSOStatus)
def sso_status(
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
):
    tenant = _resolve_tenant(db, tenant_id)
    if not tenant:
        return TenantSSOStatus(enabled=False, sso_required=False)
    config = get_sso_config(db, tenant.id)
    if not config or not config.is_enabled or config.provider != "oidc":
        return TenantSSOStatus(enabled=False, sso_required=False)
    return TenantSSOStatus(enabled=True, sso_required=bool(config.sso_required))


@router.get("/start")
def oidc_start(
    tenant_id: str,
    next: str | None = None,
    db: Session = Depends(get_db),
):
    tenant = _resolve_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    config = get_sso_config(db, tenant.id)
    if not config or not config.is_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO not enabled")
    if config.provider != "oidc":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO provider not supported")
    if not config.issuer_url or not config.client_id or not config.redirect_uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC configuration incomplete")

    discovery = fetch_discovery(config.issuer_url)
    nonce = generate_nonce()
    next_path = sanitize_next_path(next) or "/sso/callback"
    state = create_state_token(tenant.id, nonce=nonce, next_path=next_path)
    authorize_url = build_authorize_url(
        discovery=discovery,
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        scope=config.scopes,
        state=state,
        nonce=nonce,
    )
    return RedirectResponse(authorize_url)


@router.get("/callback")
def oidc_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state")

    try:
        state_payload = decode_state_token(state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    tenant_id = state_payload.get("tenant_id")
    nonce = state_payload.get("nonce")
    next_path = (
        state_payload.get("next")
        if isinstance(state_payload.get("next"), str)
        else "/sso/callback"
    )
    if not tenant_id or not nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SSO state")

    tenant = get_tenant_by_id(db, int(tenant_id))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    config = get_sso_config(db, tenant.id)
    if not config or not config.is_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO not enabled")
    if config.provider != "oidc":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO provider not supported")
    if not config.issuer_url or not config.client_id or not config.redirect_uri:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC configuration incomplete")

    discovery = fetch_discovery(config.issuer_url)
    client_secret = decrypt_client_secret(config.client_secret_enc)
    if not client_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC client secret missing")
    try:
        tokens = exchange_code_for_tokens(
            discovery=discovery,
            client_id=config.client_id,
            client_secret=client_secret,
            redirect_uri=config.redirect_uri,
            code=code,
        )
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("Missing id_token")
        claims = verify_id_token(
            id_token=id_token,
            discovery=discovery,
            client_id=config.client_id,
            nonce=str(nonce),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC email claim required")
    if not _email_domain_allowed(email, config.allowed_email_domains or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email domain not allowed")

    user = get_user_by_username(db, email)
    if not user:
        if not config.auto_provision:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User provisioning disabled")
        password = secrets.token_urlsafe(32)
        user = create_user(db, username=email, password_hash=get_password_hash(password))

    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == tenant.id,
            Membership.user_id == user.id,
        )
        .first()
    )
    if not membership:
        if not config.auto_provision:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership required")
        membership = create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role="viewer",
            created_by_user_id=user.id,
        )
    if membership.status != MembershipStatusEnum.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership inactive")

    access_token = create_access_token(
        data={"sub": user.username, "memberships": _membership_snapshot(db, user.id)},
        expires_delta=None,
    )
    create_audit_log(
        db,
        tenant_id=tenant.id,
        username=user.username,
        event="auth.sso.login.success",
        request=None,
    )

    base_url = settings.FRONTEND_BASE_URL.rstrip("/")
    target = sanitize_next_path(next_path) or "/sso/callback"
    fragment = urlencode(
        {
            "sso_token": access_token,
            "sso_user": user.username,
            "tenant": tenant.slug,
        }
    )
    return RedirectResponse(f"{base_url}{target}#{fragment}")
