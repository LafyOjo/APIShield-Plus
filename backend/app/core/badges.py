from __future__ import annotations

import secrets
from dataclasses import dataclass
import hmac
import hashlib
import time
from typing import Any

from app.core.crypto import decrypt_json, encrypt_json
from app.models.trust_badges import TrustBadgeConfig


ALLOWED_BADGE_STYLES = {"light", "dark", "minimal"}
FREE_BADGE_STYLES = {"light"}
BADGE_BRANDING_REQUIRED_PLANS = {"", None, "free", "starter"}


@dataclass
class BadgeKey:
    raw: str
    encrypted: str


def generate_badge_key() -> BadgeKey:
    raw = secrets.token_urlsafe(32)
    encrypted = encrypt_json({"key": raw})
    return BadgeKey(raw=raw, encrypted=encrypted)


def extract_badge_key(config: TrustBadgeConfig) -> str:
    if not config or not config.badge_key_enc:
        raise ValueError("Badge key not configured")
    payload = decrypt_json(config.badge_key_enc)
    key = payload.get("key") if isinstance(payload, dict) else None
    if not key:
        raise ValueError("Invalid badge key payload")
    return str(key)


def normalize_style(value: str | None) -> str:
    if not value:
        return "light"
    normalized = value.strip().lower()
    return normalized if normalized in ALLOWED_BADGE_STYLES else "light"


def apply_badge_plan_constraints(config: TrustBadgeConfig, plan_key: str | None) -> None:
    plan = (plan_key or "").strip().lower()
    config.style = normalize_style(config.style)
    if plan in BADGE_BRANDING_REQUIRED_PLANS:
        config.show_branding = True
        if config.style not in FREE_BADGE_STYLES:
            config.style = "light"


def apply_badge_policy_to_payload(payload: dict[str, Any], plan_key: str | None) -> dict[str, Any]:
    plan = (plan_key or "").strip().lower()
    normalized = normalize_style(payload.get("style"))
    show_branding = bool(payload.get("show_branding", True))
    if plan in BADGE_BRANDING_REQUIRED_PLANS:
        show_branding = True
        if normalized not in FREE_BADGE_STYLES:
            normalized = "light"
    payload["style"] = normalized
    payload["show_branding"] = show_branding
    return payload


def serialize_badge_config(config: TrustBadgeConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "tenant_id": config.tenant_id,
        "website_id": config.website_id,
        "is_enabled": config.is_enabled,
        "style": config.style,
        "show_score": config.show_score,
        "show_branding": config.show_branding,
        "clickthrough_url": config.clickthrough_url,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def sign_badge_request(website_id: int, ts: int, key: str) -> str:
    message = f"{website_id}:{ts}".encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest


def verify_badge_signature(website_id: int, ts: int, sig: str, key: str, *, ttl_seconds: int) -> bool:
    if not sig:
        return False
    now = int(time.time())
    if abs(now - ts) > ttl_seconds:
        return False
    expected = sign_badge_request(website_id, ts, key)
    return hmac.compare_digest(expected, sig)
