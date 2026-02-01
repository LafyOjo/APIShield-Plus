from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.marketplace import MarketplaceTemplate


CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
OFFICIAL_SOURCE = "official"


def load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _find_existing(db, *, template_type: str, title: str, stack_type: str | None, source: str) -> MarketplaceTemplate | None:
    return (
        db.query(MarketplaceTemplate)
        .filter(
            MarketplaceTemplate.template_type == template_type,
            MarketplaceTemplate.title == title,
            MarketplaceTemplate.stack_type == stack_type,
            MarketplaceTemplate.source == source,
        )
        .first()
    )


def seed_catalog(db) -> list[MarketplaceTemplate]:
    templates: list[MarketplaceTemplate] = []
    for entry in load_catalog():
        template_type = str(entry.get("template_type") or "").strip().lower()
        title = str(entry.get("title") or "").strip()
        if not template_type or not title:
            continue
        stack_type = entry.get("stack_type")
        if isinstance(stack_type, str):
            stack_type = stack_type.strip().lower() or None
        source = (entry.get("source") or OFFICIAL_SOURCE).strip().lower()
        if source != OFFICIAL_SOURCE:
            source = OFFICIAL_SOURCE
        status = (entry.get("status") or "published").strip().lower()
        template = _find_existing(
            db,
            template_type=template_type,
            title=title,
            stack_type=stack_type,
            source=source,
        )
        if template is None:
            template = MarketplaceTemplate(
                template_type=template_type,
                title=title,
                stack_type=stack_type,
                source=source,
            )
            db.add(template)

        template.description = entry.get("description") or ""
        template.tags = entry.get("tags") or []
        template.content_json = entry.get("content_json") or {}
        template.status = status
        template.safety_notes = entry.get("safety_notes")
        templates.append(template)

    db.commit()
    for template in templates:
        db.refresh(template)
    return templates


def ensure_catalog_seeded(db) -> list[MarketplaceTemplate]:
    existing = (
        db.query(MarketplaceTemplate)
        .filter(MarketplaceTemplate.source == OFFICIAL_SOURCE)
        .count()
    )
    if existing == 0:
        return seed_catalog(db)
    return seed_catalog(db)
