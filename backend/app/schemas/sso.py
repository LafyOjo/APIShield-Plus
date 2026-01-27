from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, root_validator, validator


class TenantSSOConfigBase(BaseModel):
    provider: Literal["oidc", "saml"] = Field(default="oidc")
    is_enabled: bool = False
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    scopes: Optional[str] = "openid email profile"
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_x509_cert: Optional[str] = None
    sp_entity_id: Optional[str] = None
    sp_acs_url: Optional[str] = None
    sp_x509_cert: Optional[str] = None
    allowed_email_domains: Optional[List[str]] = None
    sso_required: bool = False
    auto_provision: bool = False

    @validator("issuer_url", "redirect_uri", "idp_sso_url", "sp_acs_url", pre=True)
    def _strip_urls(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @validator("idp_x509_cert", "sp_x509_cert", pre=True)
    def _strip_cert(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @validator("allowed_email_domains", pre=True)
    def _normalize_domains(cls, value):
        if value is None:
            return None
        return [str(domain).strip().lower() for domain in value if str(domain).strip()]

    @root_validator(skip_on_failure=True)
    def _validate_provider_fields(cls, values):
        provider = values.get("provider", "oidc")
        if provider == "oidc":
            missing = [
                field
                for field in ("issuer_url", "client_id", "redirect_uri")
                if not values.get(field)
            ]
            if missing:
                raise ValueError(f"Missing required OIDC fields: {', '.join(missing)}")
            if not values.get("scopes"):
                values["scopes"] = "openid email profile"
        elif provider == "saml":
            missing = [
                field
                for field in ("idp_entity_id", "idp_sso_url", "idp_x509_cert", "sp_entity_id", "sp_acs_url")
                if not values.get(field)
            ]
            if missing:
                raise ValueError(f"Missing required SAML fields: {', '.join(missing)}")
        else:
            raise ValueError("Unsupported SSO provider")
        return values


class TenantSSOConfigUpsert(TenantSSOConfigBase):
    client_secret: Optional[str] = None


class TenantSSOConfigRead(BaseModel):
    provider: str
    is_enabled: bool
    issuer_url: Optional[str]
    client_id: Optional[str]
    redirect_uri: Optional[str]
    scopes: Optional[str]
    idp_entity_id: Optional[str]
    idp_sso_url: Optional[str]
    idp_x509_cert: Optional[str]
    sp_entity_id: Optional[str]
    sp_acs_url: Optional[str]
    sp_x509_cert: Optional[str]
    allowed_email_domains: Optional[List[str]]
    sso_required: bool
    auto_provision: bool
    last_tested_at: Optional[datetime]
    last_error: Optional[str]

    class Config:
        orm_mode = True


class TenantSSOStatus(BaseModel):
    enabled: bool
    sso_required: bool


class TenantSSOTestResponse(BaseModel):
    ok: bool
    issuer: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    error: Optional[str] = None
