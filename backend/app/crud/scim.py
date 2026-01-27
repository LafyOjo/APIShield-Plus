from sqlalchemy.orm import Session

from app.core.scim import generate_scim_token, hash_scim_token, verify_scim_token
from app.models.enums import RoleEnum
from app.models.scim_mappings import SCIMExternalUserMap
from app.models.tenant_scim import TenantSCIMConfig


ALLOWED_SCIM_ROLES = {
    RoleEnum.VIEWER,
    RoleEnum.ANALYST,
    RoleEnum.SECURITY_ADMIN,
    RoleEnum.BILLING_ADMIN,
    RoleEnum.ADMIN,
}


def _normalize_role(role: str | RoleEnum | None) -> RoleEnum:
    if role is None:
        return RoleEnum.VIEWER
    if isinstance(role, RoleEnum):
        return role
    try:
        return RoleEnum(role)
    except ValueError as exc:
        raise ValueError("Invalid role") from exc


def get_scim_config(db: Session, tenant_id: int) -> TenantSCIMConfig | None:
    return (
        db.query(TenantSCIMConfig)
        .filter(TenantSCIMConfig.tenant_id == tenant_id)
        .first()
    )


def upsert_scim_config(
    db: Session,
    tenant_id: int,
    *,
    is_enabled: bool,
    default_role: str | RoleEnum | None,
    group_role_mappings: dict | None,
) -> TenantSCIMConfig:
    config = get_scim_config(db, tenant_id)
    if not config:
        config = TenantSCIMConfig(tenant_id=tenant_id)
        db.add(config)

    normalized_role = _normalize_role(default_role)
    if normalized_role not in ALLOWED_SCIM_ROLES:
        raise ValueError("Default role must be viewer, analyst, or admin")

    config.is_enabled = bool(is_enabled)
    config.default_role = normalized_role.value
    config.group_role_mappings_json = group_role_mappings
    db.commit()
    db.refresh(config)
    return config


def rotate_scim_token(db: Session, tenant_id: int) -> tuple[TenantSCIMConfig, str]:
    config = get_scim_config(db, tenant_id)
    if not config:
        config = TenantSCIMConfig(tenant_id=tenant_id, is_enabled=True)
        db.add(config)
    token = generate_scim_token()
    config.scim_token_hash = hash_scim_token(token)
    config.token_last_rotated_at = None
    config.is_enabled = True
    db.commit()
    db.refresh(config)
    return config, token


def verify_scim_bearer(db: Session, tenant_id: int, token: str) -> bool:
    config = get_scim_config(db, tenant_id)
    if not config or not config.is_enabled or not config.scim_token_hash:
        return False
    return verify_scim_token(token, config.scim_token_hash)


def get_scim_user_map(db: Session, tenant_id: int, scim_user_id: str) -> SCIMExternalUserMap | None:
    return (
        db.query(SCIMExternalUserMap)
        .filter(
            SCIMExternalUserMap.tenant_id == tenant_id,
            SCIMExternalUserMap.scim_user_id == scim_user_id,
        )
        .first()
    )


def get_scim_user_map_by_user(db: Session, tenant_id: int, user_id: int) -> SCIMExternalUserMap | None:
    return (
        db.query(SCIMExternalUserMap)
        .filter(
            SCIMExternalUserMap.tenant_id == tenant_id,
            SCIMExternalUserMap.user_id == user_id,
        )
        .first()
    )


def create_scim_user_map(
    db: Session,
    tenant_id: int,
    scim_user_id: str,
    user_id: int,
) -> SCIMExternalUserMap:
    mapping = SCIMExternalUserMap(
        tenant_id=tenant_id,
        scim_user_id=scim_user_id,
        user_id=user_id,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping
