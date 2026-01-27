from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.incidents import Incident
from app.models.remediation_playbooks import RemediationPlaybook
from app.models.website_stack_profiles import WebsiteStackProfile


logger = logging.getLogger(__name__)

TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"

PLAYBOOK_STATUS_DRAFT = "draft"

INCIDENT_TEMPLATE_KEYS = {
    "credential_stuffing": "credential_stuffing",
    "brute_force_login": "brute_force_login",
    "csp_integrity": "csp_hardening",
    "script_injection": "script_injection",
    "checkout_js_errors": "checkout_js_errors",
    "generic": "generic",
}

STACK_TEMPLATE_OVERRIDES = {
    ("shopify", "script_injection"): "theme_injection",
    ("custom", "credential_stuffing"): "rate_limit_nginx",
}


def _extract_event_keys(incident: Incident) -> list[str]:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    event_counts = evidence.get("event_types")
    if not isinstance(event_counts, dict):
        return []
    return [str(key).lower() for key in event_counts.keys()]


def _extract_signal_keys(incident: Incident) -> list[str]:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    signals = evidence.get("signal_types")
    if not isinstance(signals, dict):
        return []
    return [str(key).lower() for key in signals.keys()]


def classify_incident(incident: Incident) -> str:
    event_types = _extract_event_keys(incident)
    signal_types = _extract_signal_keys(incident)
    title = f"{incident.title} {incident.summary or ''}".lower()

    if any("credential" in key or "stuff" in key for key in event_types) or "credential" in title:
        return "credential_stuffing"
    if any("brute" in key for key in event_types) or "brute" in title or incident.category == "login":
        return "brute_force_login"
    if any("csp" in key or "integrity" in key for key in event_types) or incident.category == "integrity":
        return "csp_integrity"
    if any("script" in key or "injection" in key for key in event_types) or "script injection" in title:
        return "script_injection"
    if (
        any("js_error" in key or key == "error" for key in event_types)
        or any("js_error" in key for key in signal_types)
        or "conversion" in title
    ):
        return "checkout_js_errors"
    return "generic"


def _read_template_file(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*(.*?)```", content, re.DOTALL)
    if not match:
        raise ValueError(f"Template {path} missing json payload")
    payload = match.group(1).strip()
    return json.loads(payload)


def _resolve_template(stack_type: str, template_key: str) -> tuple[dict[str, Any], str]:
    stack = (stack_type or "custom").strip().lower()
    template_name = INCIDENT_TEMPLATE_KEYS.get(template_key, "generic")
    override = STACK_TEMPLATE_OVERRIDES.get((stack, template_key))
    if override:
        template_name = override

    primary = TEMPLATE_ROOT / stack / f"{template_name}.md"
    if primary.exists():
        return _read_template_file(primary), stack

    fallback = TEMPLATE_ROOT / "custom" / f"{template_name}.md"
    if fallback.exists():
        return _read_template_file(fallback), "custom"

    generic = TEMPLATE_ROOT / "custom" / "generic.md"
    if generic.exists():
        return _read_template_file(generic), "custom"

    raise FileNotFoundError(f"Playbook template not found for {stack}:{template_name}")


def _normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
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


def _append_prescription_section(sections: list[dict[str, Any]], prescriptions: list[dict[str, Any]]) -> None:
    if not prescriptions:
        return
    steps = []
    for item in prescriptions:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("id") or "Prescription")
        why = item.get("why_it_matters")
        if why:
            steps.append(f"{title} - {why}")
        else:
            steps.append(title)
    if not steps:
        return
    sections.append(
        {
            "title": "Related prescriptions",
            "context": "These actions were generated from the incident evidence and should be validated against the stack.",
            "steps": steps,
            "code_snippets": [],
            "verification_steps": ["Confirm the steps align with your deployment workflow."],
            "rollback_steps": ["Revert any configuration changes if they introduce new errors."],
            "risk_level": "medium",
        }
    )


def get_latest_playbook(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
    stack_type: str | None = None,
) -> RemediationPlaybook | None:
    query = db.query(RemediationPlaybook).filter(
        RemediationPlaybook.tenant_id == tenant_id,
        RemediationPlaybook.incident_id == incident_id,
    )
    if stack_type:
        query = query.filter(RemediationPlaybook.stack_type == stack_type)
    return query.order_by(RemediationPlaybook.version.desc()).first()


def generate_playbook_for_incident(
    db: Session,
    *,
    incident: Incident,
    stack_profile: WebsiteStackProfile | None,
    prescriptions: list[dict[str, Any]] | None = None,
) -> RemediationPlaybook:
    stack_type = (stack_profile.stack_type if stack_profile else "custom") or "custom"
    template_key = classify_incident(incident)
    template_payload, resolved_stack = _resolve_template(stack_type, template_key)
    sections = _normalize_sections(template_payload.get("sections") or [])
    _append_prescription_section(sections, prescriptions or [])

    version = int(template_payload.get("version") or 1)

    playbook = RemediationPlaybook(
        tenant_id=incident.tenant_id,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        incident_id=incident.id,
        stack_type=resolved_stack,
        status=PLAYBOOK_STATUS_DRAFT,
        version=version,
        sections_json=sections,
    )
    db.add(playbook)
    db.commit()
    db.refresh(playbook)
    return playbook


def get_or_generate_playbook(
    db: Session,
    *,
    incident: Incident,
    stack_profile: WebsiteStackProfile | None,
    prescriptions: list[dict[str, Any]] | None = None,
) -> RemediationPlaybook | None:
    stack_type = (stack_profile.stack_type if stack_profile else "custom") or "custom"
    existing = get_latest_playbook(
        db,
        tenant_id=incident.tenant_id,
        incident_id=incident.id,
        stack_type=stack_type,
    )
    if existing:
        return existing

    try:
        return generate_playbook_for_incident(
            db,
            incident=incident,
            stack_profile=stack_profile,
            prescriptions=prescriptions,
        )
    except Exception:
        logger.exception("Failed to generate remediation playbook")
        return None
