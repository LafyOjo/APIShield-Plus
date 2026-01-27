"""
Startup-time security checks for required configuration.
"""

from __future__ import annotations

from app.core.config import settings


def _is_production() -> bool:
    env = (settings.ENVIRONMENT or "").strip().lower()
    return env in {"production", "prod"}


def _has_placeholder_secret(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    return lowered in {"changeme", "super-secret-key", "secret", "demo-key"}


def run_startup_checks() -> None:
    missing: list[str] = []
    insecure: list[str] = []

    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL")
    if not settings.SECRET_KEY:
        missing.append("SECRET_KEY")

    if _is_production():
        if _has_placeholder_secret(settings.SECRET_KEY) or len(settings.SECRET_KEY or "") < 32:
            insecure.append("SECRET_KEY")
        if not settings.ZERO_TRUST_API_KEY:
            missing.append("ZERO_TRUST_API_KEY")
        if not settings.INTEGRATION_ENCRYPTION_KEY:
            missing.append("INTEGRATION_ENCRYPTION_KEY")
        if settings.API_KEY_SECRET_RETURN_IN_RESPONSE:
            insecure.append("API_KEY_SECRET_RETURN_IN_RESPONSE")
        if settings.INVITE_TOKEN_RETURN_IN_RESPONSE:
            insecure.append("INVITE_TOKEN_RETURN_IN_RESPONSE")

    if settings.GEO_PROVIDER and settings.GEO_PROVIDER.lower() == "api":
        if not settings.GEO_API_KEY:
            missing.append("GEO_API_KEY")
        if not settings.GEO_API_BASE_URL:
            missing.append("GEO_API_BASE_URL")

    if settings.STRIPE_SECRET_KEY and not settings.STRIPE_WEBHOOK_SECRET:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if settings.STRIPE_WEBHOOK_SECRET and not settings.STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")

    if missing or insecure:
        parts = []
        if missing:
            parts.append(f"Missing required settings: {', '.join(sorted(set(missing)))}")
        if insecure:
            parts.append(f"Insecure settings detected: {', '.join(sorted(set(insecure)))}")
        raise RuntimeError("Startup checks failed. " + " ".join(parts))
