from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.badges import apply_badge_plan_constraints, generate_badge_key, normalize_style
from app.crud.websites import get_website
from app.models.trust_badges import TrustBadgeConfig


def get_badge_config(db: Session, tenant_id: int, website_id: int) -> TrustBadgeConfig | None:
    return (
        db.query(TrustBadgeConfig)
        .filter(
            TrustBadgeConfig.tenant_id == tenant_id,
            TrustBadgeConfig.website_id == website_id,
        )
        .first()
    )


def get_or_create_badge_config(
    db: Session,
    tenant_id: int,
    website_id: int,
) -> TrustBadgeConfig:
    config = get_badge_config(db, tenant_id, website_id)
    if config:
        return config
    get_website(db, tenant_id, website_id)
    key = generate_badge_key()
    config = TrustBadgeConfig(
        tenant_id=tenant_id,
        website_id=website_id,
        badge_key_enc=key.encrypted,
        is_enabled=False,
        style="light",
        show_score=True,
        show_branding=True,
        clickthrough_url=None,
    )
    db.add(config)
    try:
        db.commit()
        db.refresh(config)
        return config
    except IntegrityError:
        db.rollback()
        existing = get_badge_config(db, tenant_id, website_id)
        if existing:
            return existing
        raise


def upsert_badge_config(
    db: Session,
    tenant_id: int,
    website_id: int,
    updates: dict[str, Any],
    *,
    plan_key: str | None,
) -> TrustBadgeConfig:
    config = get_or_create_badge_config(db, tenant_id, website_id)
    if "is_enabled" in updates:
        config.is_enabled = bool(updates["is_enabled"])
    if "style" in updates:
        config.style = normalize_style(updates["style"])
    if "show_score" in updates:
        config.show_score = bool(updates["show_score"])
    if "show_branding" in updates:
        config.show_branding = bool(updates["show_branding"])
    if "clickthrough_url" in updates:
        config.clickthrough_url = updates["clickthrough_url"]

    apply_badge_plan_constraints(config, plan_key)
    db.commit()
    db.refresh(config)
    return config
