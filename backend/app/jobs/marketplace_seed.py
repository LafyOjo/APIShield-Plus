from __future__ import annotations

from sqlalchemy.orm import Session

from app.marketplace.catalog import ensure_catalog_seeded


def run_marketplace_seed(db: Session) -> int:
    templates = ensure_catalog_seeded(db)
    return len(templates)
