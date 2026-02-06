from __future__ import annotations

import secrets
from typing import Any


ALLOWED_BADGE_BRANDING_MODES = {"your_brand", "co_brand", "white_label"}
FREE_BRANDING_PLANS = {"", None, "free", "pro", "starter"}
BUSINESS_BRANDING_PLANS = {"business"}
ENTERPRISE_BRANDING_PLANS = {"enterprise"}


def normalize_badge_branding_mode(value: str | None) -> str:
    if not value:
        return "your_brand"
    normalized = value.strip().lower()
    return normalized if normalized in ALLOWED_BADGE_BRANDING_MODES else "your_brand"


def apply_branding_plan_constraints(config, plan_key: str | None) -> None:
    plan = (plan_key or "").strip().lower()
    config.badge_branding_mode = normalize_badge_branding_mode(config.badge_branding_mode)
    if plan in FREE_BRANDING_PLANS:
        config.is_enabled = False
        config.badge_branding_mode = "your_brand"
        config.custom_domain = None
        config.domain_verified_at = None
        config.domain_verification_token = None
        return
    if plan in BUSINESS_BRANDING_PLANS and config.badge_branding_mode == "white_label":
        config.badge_branding_mode = "co_brand"


def apply_branding_policy_to_payload(payload: dict[str, Any], plan_key: str | None) -> dict[str, Any]:
    plan = (plan_key or "").strip().lower()
    payload["badge_branding_mode"] = normalize_badge_branding_mode(payload.get("badge_branding_mode"))
    if plan in FREE_BRANDING_PLANS:
        payload["is_enabled"] = False
        payload["badge_branding_mode"] = "your_brand"
        payload["custom_domain"] = None
        payload["domain_verified_at"] = None
        return payload
    if plan in BUSINESS_BRANDING_PLANS and payload["badge_branding_mode"] == "white_label":
        payload["badge_branding_mode"] = "co_brand"
    return payload


def resolve_effective_badge_branding_mode(mode: str | None, plan_key: str | None) -> str:
    payload = apply_branding_policy_to_payload(
        {"badge_branding_mode": mode or "your_brand", "is_enabled": True},
        plan_key,
    )
    return payload.get("badge_branding_mode") or "your_brand"


def generate_domain_verification_token() -> str:
    return secrets.token_urlsafe(16)


def build_domain_verification_record(custom_domain: str | None, token: str | None) -> tuple[str | None, str | None]:
    if not custom_domain or not token:
        return None, None
    domain = custom_domain.strip().lower()
    name = f"_apishield-verify.{domain}".strip(".")
    value = f"apishield-verify={token}"
    return name, value


def format_badge_brand_label(mode: str | None, brand_name: str | None) -> str:
    normalized = normalize_badge_branding_mode(mode)
    safe_brand = (brand_name or "").strip()
    if normalized == "white_label":
        if safe_brand:
            return f"Security monitored by {safe_brand}"
        return "Security monitored"
    if normalized == "co_brand":
        if safe_brand:
            return f"Security monitored by {safe_brand} · APIShield+"
        return "Security monitored by APIShield+"
    return "Security monitored by APIShield+"
