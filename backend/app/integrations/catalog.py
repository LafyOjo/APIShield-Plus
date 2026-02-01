from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.integration_directory import IntegrationListing


CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"


def load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def seed_catalog(db) -> list[IntegrationListing]:
    listings: list[IntegrationListing] = []
    for entry in load_catalog():
        key = str(entry.get("key") or "").strip()
        if not key:
            continue
        listing = db.query(IntegrationListing).filter(IntegrationListing.key == key).first()
        if listing is None:
            listing = IntegrationListing(key=key)
            db.add(listing)
        listing.name = entry.get("name") or key
        listing.category = entry.get("category") or "other"
        listing.description = entry.get("description") or ""
        listing.docs_url = entry.get("docs_url")
        listing.install_type = entry.get("install_type") or "snippet"
        listing.is_featured = bool(entry.get("is_featured"))
        listing.plan_required = entry.get("plan_required")
        listing.install_url = entry.get("install_url")
        listing.copy_payload = entry.get("copy_payload")
        listing.stack_types = entry.get("stack_types") or []
        listings.append(listing)
    db.commit()
    for listing in listings:
        db.refresh(listing)
    return listings


def ensure_catalog_seeded(db) -> list[IntegrationListing]:
    existing = db.query(IntegrationListing).count()
    if existing == 0:
        return seed_catalog(db)
    # If catalog file changed, refresh entries too.
    return seed_catalog(db)
