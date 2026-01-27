from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.website_stack_profiles import WebsiteStackProfile
from app.stack.detect import detect_stack_from_hints


def get_stack_profile(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
) -> WebsiteStackProfile | None:
    return (
        db.query(WebsiteStackProfile)
        .filter(
            WebsiteStackProfile.tenant_id == tenant_id,
            WebsiteStackProfile.website_id == website_id,
        )
        .first()
    )


def get_or_create_stack_profile(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
) -> WebsiteStackProfile:
    profile = get_stack_profile(db, tenant_id=tenant_id, website_id=website_id)
    if profile:
        return profile
    profile = WebsiteStackProfile(
        tenant_id=tenant_id,
        website_id=website_id,
        stack_type="custom",
        confidence=0.2,
        detected_signals_json={},
        manual_override=False,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def apply_stack_detection(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    hints: dict | None,
) -> WebsiteStackProfile:
    detection = detect_stack_from_hints(hints)
    profile = get_stack_profile(db, tenant_id=tenant_id, website_id=website_id)
    if profile is None:
        profile = WebsiteStackProfile(
            tenant_id=tenant_id,
            website_id=website_id,
            stack_type=detection.stack_type,
            confidence=detection.confidence,
            detected_signals_json=detection.signals,
            manual_override=False,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    if profile.manual_override:
        profile.detected_signals_json = detection.signals
        db.commit()
        db.refresh(profile)
        return profile

    profile.stack_type = detection.stack_type
    profile.confidence = detection.confidence
    profile.detected_signals_json = detection.signals
    profile.manual_override = False
    db.commit()
    db.refresh(profile)
    return profile


def set_stack_manual_override(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    stack_type: str,
) -> WebsiteStackProfile:
    profile = get_or_create_stack_profile(db, tenant_id=tenant_id, website_id=website_id)
    profile.stack_type = stack_type
    profile.confidence = 1.0
    profile.manual_override = True
    db.commit()
    db.refresh(profile)
    return profile


def clear_stack_manual_override(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
) -> WebsiteStackProfile:
    profile = get_or_create_stack_profile(db, tenant_id=tenant_id, website_id=website_id)
    profile.manual_override = False
    detection = detect_stack_from_hints(
        (profile.detected_signals_json or {}).get("hints")
        if isinstance(profile.detected_signals_json, dict)
        else None
    )
    profile.stack_type = detection.stack_type
    profile.confidence = detection.confidence
    profile.detected_signals_json = detection.signals
    db.commit()
    db.refresh(profile)
    return profile
