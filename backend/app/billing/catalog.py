from typing import Optional

from app.core.config import settings


_PLAN_NAME_MAP = {
    "free": "Free",
    "pro": "Pro",
    "business": "Business",
    "enterprise": "Enterprise",
    "starter": "Starter",
}


def normalize_plan_key(value: str | None) -> Optional[str]:
    if not value:
        return None
    return value.strip().lower()


def plan_key_from_plan_name(plan_name: str | None) -> Optional[str]:
    if not plan_name:
        return None
    normalized = plan_name.strip().lower()
    for key, name in _PLAN_NAME_MAP.items():
        if name.lower() == normalized:
            return key
    return normalized


def get_plan_name(plan_key: str) -> Optional[str]:
    normalized = normalize_plan_key(plan_key)
    if not normalized:
        return None
    return _PLAN_NAME_MAP.get(normalized)


def get_plan_catalog() -> dict[str, dict[str, Optional[str]]]:
    return {
        "free": {"plan_name": "Free", "price_id": None},
        "pro": {"plan_name": "Pro", "price_id": settings.STRIPE_PRICE_ID_PRO},
        "business": {"plan_name": "Business", "price_id": settings.STRIPE_PRICE_ID_BUSINESS},
        "enterprise": {"plan_name": "Enterprise", "price_id": settings.STRIPE_PRICE_ID_ENTERPRISE},
    }


def get_price_id(plan_key: str) -> Optional[str]:
    catalog = get_plan_catalog()
    entry = catalog.get(normalize_plan_key(plan_key) or "")
    return entry.get("price_id") if entry else None


def plan_key_from_price_id(price_id: str | None) -> Optional[str]:
    if not price_id:
        return None
    catalog = get_plan_catalog()
    for key, entry in catalog.items():
        if entry.get("price_id") == price_id:
            return key
    return None
