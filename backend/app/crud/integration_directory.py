from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.crud.websites import get_website
from app.integrations.catalog import ensure_catalog_seeded
from app.models.integration_directory import IntegrationInstallEvent, IntegrationListing
from app.tenancy.errors import TenantNotFound


ALLOWED_INTEGRATION_CATEGORIES = {
    "cms",
    "ecommerce",
    "frontend",
    "security",
    "observability",
    "other",
}

ALLOWED_INSTALL_TYPES = {
    "plugin",
    "app",
    "snippet",
    "config",
}

ALLOWED_INSTALL_METHODS = {
    "clicked",
    "copy",
    "download",
}


def list_listings(db: Session) -> list[IntegrationListing]:
    ensure_catalog_seeded(db)
    return db.query(IntegrationListing).order_by(IntegrationListing.is_featured.desc(), IntegrationListing.name).all()


def get_listing(db: Session, key: str) -> IntegrationListing | None:
    ensure_catalog_seeded(db)
    return db.query(IntegrationListing).filter(IntegrationListing.key == key).first()


def create_install_event(
    db: Session,
    *,
    tenant_id: int,
    integration_key: str,
    website_id: int | None,
    method: str,
    metadata: dict[str, Any] | None,
) -> IntegrationInstallEvent:
    listing = get_listing(db, integration_key)
    if listing is None:
        raise ValueError("Unknown integration key")
    normalized_method = method.strip().lower()
    if normalized_method not in ALLOWED_INSTALL_METHODS:
        raise ValueError("Invalid install method")
    if website_id is not None:
        try:
            get_website(db, tenant_id, website_id)
        except TenantNotFound as exc:
            raise ValueError("Website not found for tenant") from exc
    event = IntegrationInstallEvent(
        tenant_id=tenant_id,
        website_id=website_id,
        integration_key=integration_key,
        installed_at=utcnow(),
        method=normalized_method,
        metadata_json=metadata or {},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def serialize_listing(listing: IntegrationListing) -> dict[str, Any]:
    return {
        "key": listing.key,
        "name": listing.name,
        "category": listing.category,
        "description": listing.description,
        "docs_url": listing.docs_url,
        "install_type": listing.install_type,
        "is_featured": listing.is_featured,
        "plan_required": listing.plan_required,
        "install_url": listing.install_url,
        "copy_payload": listing.copy_payload,
        "stack_types": listing.stack_types or [],
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
    }
