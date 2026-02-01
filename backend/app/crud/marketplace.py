from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.crud.notification_rules import create_rule
from app.marketplace.catalog import ensure_catalog_seeded
from app.models.incidents import Incident
from app.models.marketplace import MarketplaceTemplate, TemplateImportEvent
from app.models.protection_presets import ProtectionPreset
from app.models.remediation_playbooks import RemediationPlaybook


ALLOWED_TEMPLATE_TYPES = {"playbook", "preset", "alert_rules"}
ALLOWED_TEMPLATE_STATUSES = {"draft", "published", "rejected"}
ALLOWED_TEMPLATE_SOURCES = {"official", "community"}


def _normalize_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        cleaned = []
        for item in tags:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if value:
                cleaned.append(value)
        return cleaned
    if isinstance(tags, str):
        return [value.strip() for value in tags.split(",") if value.strip()]
    return []


def _normalize_sections(sections: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(sections, list):
        return normalized
    for section in sections:
        if not isinstance(section, dict):
            continue
        normalized.append(
            {
                "title": str(section.get("title") or "Untitled"),
                "context": str(section.get("context") or ""),
                "steps": list(section.get("steps") or []),
                "code_snippets": list(section.get("code_snippets") or []),
                "verification_steps": list(section.get("verification_steps") or []),
                "rollback_steps": list(section.get("rollback_steps") or []),
                "risk_level": str(section.get("risk_level") or "medium"),
            }
        )
    return normalized


def list_templates(
    db: Session,
    *,
    published_only: bool = True,
    template_type: str | None = None,
    stack_type: str | None = None,
    search: str | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
    include_generic_stack: bool = True,
) -> list[MarketplaceTemplate]:
    ensure_catalog_seeded(db)
    query = db.query(MarketplaceTemplate)
    if published_only:
        query = query.filter(MarketplaceTemplate.status == "published")
    if template_type:
        template_type = template_type.strip().lower()
        query = query.filter(MarketplaceTemplate.template_type == template_type)
    if source:
        source = source.strip().lower()
        query = query.filter(MarketplaceTemplate.source == source)
    if stack_type:
        stack_value = stack_type.strip().lower()
        if include_generic_stack:
            query = query.filter(
                or_(
                    MarketplaceTemplate.stack_type == stack_value,
                    MarketplaceTemplate.stack_type.is_(None),
                )
            )
        else:
            query = query.filter(MarketplaceTemplate.stack_type == stack_value)
    items = query.order_by(
        MarketplaceTemplate.downloads_count.desc(),
        MarketplaceTemplate.created_at.desc(),
    ).all()

    normalized_tags = _normalize_tags(tags)
    if normalized_tags:
        items = [
            item
            for item in items
            if any(tag in (item.tags or []) for tag in normalized_tags)
        ]
    if search:
        lowered = search.strip().lower()
        if lowered:
            items = [
                item
                for item in items
                if lowered in (item.title or "").lower()
                or lowered in (item.description or "").lower()
            ]
    return items


def get_template(
    db: Session,
    template_id: int,
    *,
    published_only: bool = True,
) -> MarketplaceTemplate | None:
    ensure_catalog_seeded(db)
    query = db.query(MarketplaceTemplate).filter(MarketplaceTemplate.id == template_id)
    if published_only:
        query = query.filter(MarketplaceTemplate.status == "published")
    return query.first()


def create_template_submission(
    db: Session,
    *,
    template_type: str,
    title: str,
    description: str,
    stack_type: str | None,
    tags: list[str] | None,
    content_json: dict[str, Any],
    author_user_id: int | None,
) -> MarketplaceTemplate:
    template_type = (template_type or "").strip().lower()
    if template_type not in ALLOWED_TEMPLATE_TYPES:
        raise ValueError("Unsupported template type")
    title = (title or "").strip()
    description = (description or "").strip()
    if not title or not description:
        raise ValueError("Title and description are required")
    if not isinstance(content_json, dict):
        raise ValueError("content_json must be a JSON object")

    template = MarketplaceTemplate(
        template_type=template_type,
        title=title,
        description=description,
        stack_type=(stack_type.strip().lower() if stack_type else None),
        tags=_normalize_tags(tags),
        content_json=content_json,
        author_user_id=author_user_id,
        source="community",
        status="draft",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session,
    template_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    stack_type: str | None = None,
    tags: list[str] | None = None,
    content_json: dict[str, Any] | None = None,
    status: str | None = None,
    source: str | None = None,
    safety_notes: str | None = None,
) -> MarketplaceTemplate | None:
    template = db.query(MarketplaceTemplate).filter(MarketplaceTemplate.id == template_id).first()
    if not template:
        return None

    if title is not None:
        template.title = title.strip() or template.title
    if description is not None:
        template.description = description.strip() or template.description
    if stack_type is not None:
        template.stack_type = stack_type.strip().lower() if stack_type else None
    if tags is not None:
        template.tags = _normalize_tags(tags)
    if content_json is not None:
        if not isinstance(content_json, dict):
            raise ValueError("content_json must be a JSON object")
        template.content_json = content_json
    if status is not None:
        status_value = status.strip().lower()
        if status_value not in ALLOWED_TEMPLATE_STATUSES:
            raise ValueError("Invalid template status")
        template.status = status_value
    if source is not None:
        source_value = source.strip().lower()
        if source_value not in ALLOWED_TEMPLATE_SOURCES:
            raise ValueError("Invalid template source")
        template.source = source_value
    if safety_notes is not None:
        template.safety_notes = safety_notes

    db.commit()
    db.refresh(template)
    return template


def _build_preset_payload(template: MarketplaceTemplate) -> tuple[str, dict[str, Any]]:
    raw = template.content_json or {}
    if not isinstance(raw, dict):
        raise ValueError("Preset content must be a JSON object")

    preset_type = raw.get("preset_type") or raw.get("type")
    if "formats" in raw:
        if not preset_type:
            preset_type = raw.get("type") or raw.get("preset_type") or "preset"
        return str(preset_type), raw

    content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
    if not preset_type:
        preset_type = "preset"
    preset_type = str(preset_type)
    json_block = json.dumps(content, indent=2)
    payload = {
        "type": preset_type,
        "title": template.title,
        "summary": template.description,
        "metadata": content,
        "formats": {
            "copy_blocks": [{"label": "JSON config", "content": json_block}],
            "json": content,
            "markdown": f"# {template.title}\n\n```json\n{json_block}\n```",
        },
        "evidence": {},
    }
    return preset_type, payload


def _build_playbook(
    db: Session,
    *,
    template: MarketplaceTemplate,
    incident: Incident,
) -> RemediationPlaybook:
    content = template.content_json or {}
    if not isinstance(content, dict):
        raise ValueError("Playbook content must be a JSON object")
    sections = _normalize_sections(content.get("sections"))
    if not sections:
        raise ValueError("Playbook template missing sections")
    stack_type = content.get("stack_type") or template.stack_type or "custom"
    version = int(content.get("version") or 1)

    existing = (
        db.query(RemediationPlaybook)
        .filter(
            RemediationPlaybook.tenant_id == incident.tenant_id,
            RemediationPlaybook.incident_id == incident.id,
            RemediationPlaybook.stack_type == stack_type,
        )
        .order_by(RemediationPlaybook.version.desc())
        .first()
    )
    if existing and existing.version >= version:
        version = existing.version + 1

    playbook = RemediationPlaybook(
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        stack_type=stack_type,
        status="draft",
        version=version,
        sections_json=sections,
    )
    db.add(playbook)
    return playbook


def _build_preset(
    db: Session,
    *,
    template: MarketplaceTemplate,
    incident: Incident,
) -> ProtectionPreset:
    preset_type, payload = _build_preset_payload(template)
    existing = (
        db.query(ProtectionPreset)
        .filter(
            ProtectionPreset.tenant_id == incident.tenant_id,
            ProtectionPreset.incident_id == incident.id,
            ProtectionPreset.preset_type == preset_type,
        )
        .first()
    )
    if existing:
        raise ValueError("Preset already exists for incident")
    preset = ProtectionPreset(
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        incident_id=incident.id,
        preset_type=preset_type,
        content_json=payload,
    )
    db.add(preset)
    return preset


def import_template(
    db: Session,
    *,
    template: MarketplaceTemplate,
    tenant_id: int,
    incident_id: int | None = None,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    template_type = template.template_type
    if template_type not in ALLOWED_TEMPLATE_TYPES:
        raise ValueError("Unsupported template type")

    playbook_id = None
    preset_id = None
    rule_ids: list[int] = []

    if template_type in {"playbook", "preset"}:
        if not incident_id:
            raise ValueError("Incident ID required for this template type")
        incident = (
            db.query(Incident)
            .filter(Incident.tenant_id == tenant_id, Incident.id == incident_id)
            .first()
        )
        if not incident:
            raise ValueError("Incident not found for tenant")

    if template_type == "playbook":
        incident = (
            db.query(Incident)
            .filter(Incident.tenant_id == tenant_id, Incident.id == incident_id)
            .first()
        )
        playbook = _build_playbook(db, template=template, incident=incident)
        event = TemplateImportEvent(
            tenant_id=tenant_id,
            template_id=template.id,
            imported_at=utcnow(),
            applied_to_incident_id=incident_id,
        )
        template.downloads_count = int(template.downloads_count or 0) + 1
        db.add(event)
        db.commit()
        db.refresh(playbook)
        db.refresh(event)
        playbook_id = playbook.id
        import_event_id = event.id
        return {
            "template_id": template.id,
            "import_event_id": import_event_id,
            "playbook_id": playbook_id,
            "preset_id": None,
            "rule_ids": [],
        }

    if template_type == "preset":
        incident = (
            db.query(Incident)
            .filter(Incident.tenant_id == tenant_id, Incident.id == incident_id)
            .first()
        )
        preset = _build_preset(db, template=template, incident=incident)
        event = TemplateImportEvent(
            tenant_id=tenant_id,
            template_id=template.id,
            imported_at=utcnow(),
            applied_to_incident_id=incident_id,
        )
        template.downloads_count = int(template.downloads_count or 0) + 1
        db.add(event)
        db.commit()
        db.refresh(preset)
        db.refresh(event)
        preset_id = preset.id
        import_event_id = event.id
        return {
            "template_id": template.id,
            "import_event_id": import_event_id,
            "playbook_id": None,
            "preset_id": preset_id,
            "rule_ids": [],
        }

    if template_type == "alert_rules":
        content = template.content_json or {}
        if not isinstance(content, dict):
            raise ValueError("Alert rules template content must be a JSON object")
        rules = content.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError("Alert rules template missing rules list")

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            created = create_rule(
                db,
                tenant_id=tenant_id,
                name=str(rule.get("name") or template.title),
                trigger_type=str(rule.get("trigger_type") or ""),
                created_by_user_id=created_by_user_id,
                is_enabled=bool(rule.get("is_enabled", True)),
                filters_json=rule.get("filters"),
                thresholds_json=rule.get("thresholds"),
                quiet_hours_json=rule.get("quiet_hours"),
                route_to_channel_ids=rule.get("channel_ids"),
            )
            rule_ids.append(created.id)

        event = TemplateImportEvent(
            tenant_id=tenant_id,
            template_id=template.id,
            imported_at=utcnow(),
            applied_to_incident_id=incident_id,
        )
        template.downloads_count = int(template.downloads_count or 0) + 1
        db.add(event)
        db.commit()
        db.refresh(event)
        return {
            "template_id": template.id,
            "import_event_id": event.id,
            "playbook_id": None,
            "preset_id": None,
            "rule_ids": rule_ids,
        }

    raise ValueError("Unsupported template type")


def serialize_template(template: MarketplaceTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "template_type": template.template_type,
        "title": template.title,
        "description": template.description,
        "stack_type": template.stack_type,
        "tags": template.tags or [],
        "content_json": template.content_json or {},
        "source": template.source,
        "status": template.status,
        "safety_notes": template.safety_notes,
        "downloads_count": template.downloads_count,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
