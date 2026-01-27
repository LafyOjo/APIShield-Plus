from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.oidc import fetch_discovery
from app.crud.tenant_sso import get_sso_config, mark_sso_test_result, upsert_sso_config
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.entitlements.enforcement import require_feature
from app.entitlements.resolver import resolve_entitlements_for_tenant
from app.models.enums import RoleEnum
from app.schemas.sso import TenantSSOConfigRead, TenantSSOConfigUpsert, TenantSSOTestResponse
from app.tenancy.dependencies import require_roles
from app.api.dependencies import get_current_user


router = APIRouter(prefix="/sso", tags=["sso"])


def _resolve_tenant_id(db: Session, tenant_hint: str | None) -> int:
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


def _require_sso_feature(entitlements: dict, provider: str) -> None:
    normalized = (provider or "oidc").strip().lower()
    if normalized == "saml":
        require_feature(entitlements, "sso_saml", message="SAML SSO requires an Enterprise plan")
    else:
        require_feature(entitlements, "sso_oidc", message="OIDC SSO requires a Business plan")


@router.get("/config", response_model=TenantSSOConfigRead)
def read_sso_config(
    db: Session = Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    config = get_sso_config(db, tenant_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO config not found")
    _require_sso_feature(entitlements, config.provider)
    return config


@router.post("/config", response_model=TenantSSOConfigRead)
def upsert_sso_config_endpoint(
    payload: TenantSSOConfigUpsert,
    db: Session = Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    _require_sso_feature(entitlements, payload.provider)
    existing = get_sso_config(db, tenant_id)
    if not existing and payload.provider == "oidc" and not payload.client_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_secret is required")
    config = upsert_sso_config(
        db,
        tenant_id,
        provider=payload.provider,
        is_enabled=payload.is_enabled,
        issuer_url=payload.issuer_url,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        redirect_uri=payload.redirect_uri,
        scopes=payload.scopes,
        allowed_email_domains=payload.allowed_email_domains,
        sso_required=payload.sso_required,
        auto_provision=payload.auto_provision,
        idp_entity_id=payload.idp_entity_id,
        idp_sso_url=payload.idp_sso_url,
        idp_x509_cert=payload.idp_x509_cert,
        sp_entity_id=payload.sp_entity_id,
        sp_acs_url=payload.sp_acs_url,
        sp_x509_cert=payload.sp_x509_cert,
    )
    return config


@router.post("/config/test", response_model=TenantSSOTestResponse)
def test_sso_config(
    db: Session = Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    entitlements = resolve_entitlements_for_tenant(db, tenant_id)
    config = get_sso_config(db, tenant_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO config not found")
    _require_sso_feature(entitlements, config.provider)
    if config.provider != "oidc":
        return TenantSSOTestResponse(ok=False, error="SSO test not supported for provider")

    try:
        discovery = fetch_discovery(config.issuer_url)
        if not discovery.get("authorization_endpoint") or not discovery.get("token_endpoint"):
            raise ValueError("OIDC discovery missing required endpoints")
        mark_sso_test_result(db, config, success=True, error=None)
        return TenantSSOTestResponse(
            ok=True,
            issuer=discovery.get("issuer"),
            authorization_endpoint=discovery.get("authorization_endpoint"),
            token_endpoint=discovery.get("token_endpoint"),
            jwks_uri=discovery.get("jwks_uri"),
        )
    except Exception as exc:
        mark_sso_test_result(db, config, success=False, error=str(exc))
        return TenantSSOTestResponse(ok=False, error=str(exc))
