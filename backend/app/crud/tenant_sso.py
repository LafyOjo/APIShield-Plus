from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.core.time import utcnow
from app.models.enums import MembershipStatusEnum
from app.models.memberships import Membership
from app.models.tenant_sso import TenantSSOConfig


def get_sso_config(db: Session, tenant_id: int) -> TenantSSOConfig | None:
    return db.query(TenantSSOConfig).filter(TenantSSOConfig.tenant_id == tenant_id).first()


def _normalize_domains(domains: Iterable[str] | None) -> list[str] | None:
    if domains is None:
        return None
    normalized = {domain.strip().lower() for domain in domains if domain and domain.strip()}
    return sorted(normalized) if normalized else []


def encrypt_client_secret(raw_secret: str) -> str:
    return encrypt_json({"secret": raw_secret})


def decrypt_client_secret(encrypted: str | None) -> str:
    if not encrypted:
        return ""
    payload = decrypt_json(encrypted)
    return str(payload.get("secret", ""))


def upsert_sso_config(
    db: Session,
    tenant_id: int,
    *,
    provider: str = "oidc",
    is_enabled: bool,
    issuer_url: str | None,
    client_id: str | None,
    client_secret: str | None,
    redirect_uri: str | None,
    scopes: str | None,
    allowed_email_domains: list[str] | None,
    sso_required: bool,
    auto_provision: bool,
    idp_entity_id: str | None,
    idp_sso_url: str | None,
    idp_x509_cert: str | None,
    sp_entity_id: str | None,
    sp_acs_url: str | None,
    sp_x509_cert: str | None,
) -> TenantSSOConfig:
    config = get_sso_config(db, tenant_id)
    if not config:
        config = TenantSSOConfig(tenant_id=tenant_id)
        db.add(config)

    config.provider = provider
    config.is_enabled = is_enabled
    config.allowed_email_domains = _normalize_domains(allowed_email_domains)
    config.sso_required = sso_required
    config.auto_provision = auto_provision

    if provider == "oidc":
        config.issuer_url = issuer_url
        config.client_id = client_id
        config.redirect_uri = redirect_uri
        config.scopes = scopes
        if client_secret:
            config.client_secret_enc = encrypt_client_secret(client_secret)
    else:
        config.issuer_url = None
        config.client_id = None
        config.redirect_uri = None
        config.scopes = None
        config.client_secret_enc = encrypt_client_secret(client_secret) if client_secret else None

    if provider == "saml":
        config.idp_entity_id = idp_entity_id
        config.idp_sso_url = idp_sso_url
        config.idp_x509_cert = idp_x509_cert
        config.sp_entity_id = sp_entity_id
        config.sp_acs_url = sp_acs_url
        config.sp_x509_cert = sp_x509_cert
    else:
        config.idp_entity_id = None
        config.idp_sso_url = None
        config.idp_x509_cert = None
        config.sp_entity_id = None
        config.sp_acs_url = None
        config.sp_x509_cert = None

    db.commit()
    db.refresh(config)
    return config


def mark_sso_test_result(
    db: Session,
    config: TenantSSOConfig,
    *,
    success: bool,
    error: str | None,
) -> TenantSSOConfig:
    config.last_tested_at = utcnow()
    config.last_error = None if success else (error or "SSO test failed")
    db.commit()
    db.refresh(config)
    return config


def is_sso_required_for_user(
    db: Session,
    *,
    user_id: int,
    tenant_id: int | None,
) -> bool:
    query = (
        db.query(TenantSSOConfig)
        .join(Membership, Membership.tenant_id == TenantSSOConfig.tenant_id)
        .filter(
            Membership.user_id == user_id,
            Membership.status == MembershipStatusEnum.ACTIVE,
            TenantSSOConfig.is_enabled.is_(True),
            TenantSSOConfig.sso_required.is_(True),
        )
    )
    if tenant_id is not None:
        query = query.filter(TenantSSOConfig.tenant_id == tenant_id)
    return db.query(query.exists()).scalar()
