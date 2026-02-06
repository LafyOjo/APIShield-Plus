from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.branding import (
    apply_branding_plan_constraints,
    generate_domain_verification_token,
)
from app.models.tenant_branding import TenantBranding


def get_branding(db: Session, tenant_id: int) -> TenantBranding | None:
    return (
        db.query(TenantBranding)
        .filter(TenantBranding.tenant_id == tenant_id)
        .first()
    )


def get_or_create_branding(db: Session, tenant_id: int) -> TenantBranding:
    existing = get_branding(db, tenant_id)
    if existing:
        return existing
    branding = TenantBranding(
        tenant_id=tenant_id,
        is_enabled=False,
        badge_branding_mode="your_brand",
    )
    db.add(branding)
    db.commit()
    db.refresh(branding)
    return branding


def update_branding(
    db: Session,
    tenant_id: int,
    updates: dict[str, Any],
    *,
    plan_key: str | None,
) -> TenantBranding:
    branding = get_or_create_branding(db, tenant_id)
    if "is_enabled" in updates:
        branding.is_enabled = bool(updates["is_enabled"])
    if "brand_name" in updates:
        branding.brand_name = updates["brand_name"] or None
    if "logo_url" in updates:
        branding.logo_url = updates["logo_url"] or None
    if "primary_color" in updates:
        branding.primary_color = updates["primary_color"] or None
    if "accent_color" in updates:
        branding.accent_color = updates["accent_color"] or None
    if "badge_branding_mode" in updates:
        branding.badge_branding_mode = updates["badge_branding_mode"] or "your_brand"

    if "custom_domain" in updates:
        incoming = updates["custom_domain"]
        normalized = incoming.strip().lower() if isinstance(incoming, str) else None
        normalized = normalized or None
        if normalized != branding.custom_domain:
            branding.custom_domain = normalized
            branding.domain_verified_at = None
            branding.domain_verification_token = (
                generate_domain_verification_token() if normalized else None
            )

    apply_branding_plan_constraints(branding, plan_key)
    db.commit()
    db.refresh(branding)
    return branding


def mark_domain_verified(db: Session, tenant_id: int) -> TenantBranding:
    branding = get_or_create_branding(db, tenant_id)
    from app.core.time import utcnow

    branding.domain_verified_at = utcnow()
    db.commit()
    db.refresh(branding)
    return branding
