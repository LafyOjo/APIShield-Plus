from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem
from app.models.revenue_impact import ImpactEstimate


ActionBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def _action_credential_stuffing(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "credential_stuffing_mitigation",
        "title": "Mitigate credential stuffing on login",
        "why_it_matters": "High-volume login failures can indicate account takeover attempts.",
        "steps": [
            "Enable rate limiting per IP and per username.",
            "Add CAPTCHA or step-up challenge after repeated failures.",
            "Introduce short lockouts for high-risk attempts.",
            "Require MFA for suspicious logins.",
        ],
        "priority": "P0",
        "effort": "med",
        "expected_effect": "security",
        "evidence_links": evidence,
        "automation_possible": True,
    }


def _action_sql_injection(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "sql_injection_mitigation",
        "title": "Block SQL injection attempts",
        "why_it_matters": "Injection attempts can expose data and disrupt checkout.",
        "steps": [
            "Audit inputs for unsafe string concatenation.",
            "Parameterize queries and use prepared statements.",
            "Add or tune WAF rules for SQLi patterns.",
            "Review logs for affected endpoints and payloads.",
        ],
        "priority": "P0",
        "effort": "med",
        "expected_effect": "security",
        "evidence_links": evidence,
        "automation_possible": True,
    }


def _action_csp_hardening(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "csp_hardening",
        "title": "Harden Content Security Policy",
        "why_it_matters": "CSP violations often indicate risky scripts or inline injection.",
        "steps": [
            "Tighten script-src to trusted domains and hashes.",
            "Move new directives through report-only first.",
            "Validate third-party scripts against known inventories.",
            "Remove unexpected inline scripts or tags.",
        ],
        "priority": "P1",
        "effort": "med",
        "expected_effect": "trust",
        "evidence_links": evidence,
        "automation_possible": False,
    }


def _action_script_integrity(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "script_integrity_check",
        "title": "Verify script integrity and third-party tags",
        "why_it_matters": "Script injection can hijack user sessions or checkout flows.",
        "steps": [
            "Review recent tag manager changes and releases.",
            "Add SRI hashes for critical third-party scripts.",
            "Remove unknown tags or inline scripts.",
            "Scan for unauthorized DOM mutations.",
        ],
        "priority": "P0",
        "effort": "med",
        "expected_effect": "trust",
        "evidence_links": evidence,
        "automation_possible": False,
    }


def _action_form_submit_failure(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "form_submit_failure_investigation",
        "title": "Investigate form submission failures",
        "why_it_matters": "Submit failures directly reduce conversions and revenue.",
        "steps": [
            "Check backend endpoint errors and recent deploys.",
            "Inspect JS errors around form submission.",
            "Validate payment or auth provider connectivity.",
            "Run an end-to-end test on the affected flow.",
        ],
        "priority": "P1",
        "effort": "low",
        "expected_effect": "conversion",
        "evidence_links": evidence,
        "automation_possible": False,
    }


def _action_login_hardening(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "login_hardening",
        "title": "Harden login protections",
        "why_it_matters": "Login abuse erodes trust and increases support load.",
        "steps": [
            "Apply rate limits on login attempts.",
            "Add MFA or step-up verification on risk signals.",
            "Monitor failed login spikes and notify support.",
            "Review password policy and reset flow.",
        ],
        "priority": "P1",
        "effort": "med",
        "expected_effect": "security",
        "evidence_links": evidence,
        "automation_possible": True,
    }


def _action_threat_review(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "threat_response_review",
        "title": "Review and block malicious traffic",
        "why_it_matters": "Threat spikes can degrade performance and increase fraud risk.",
        "steps": [
            "Review the top offending IPs and paths.",
            "Add WAF rules or bot mitigations.",
            "Validate logging and alerting thresholds.",
            "Monitor for recurrence over the next 24 hours.",
        ],
        "priority": "P1",
        "effort": "med",
        "expected_effect": "security",
        "evidence_links": evidence,
        "automation_possible": True,
    }


def _action_integrity_audit(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "integrity_audit",
        "title": "Audit client integrity on affected paths",
        "why_it_matters": "Integrity issues can break critical flows and reduce trust.",
        "steps": [
            "Review CSP reports and third-party tags.",
            "Check for unauthorized script injections.",
            "Validate build artifacts and deployment pipeline.",
            "Confirm error monitoring is capturing client failures.",
        ],
        "priority": "P2",
        "effort": "med",
        "expected_effect": "trust",
        "evidence_links": evidence,
        "automation_possible": False,
    }


def _action_bot_mitigation(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "bot_mitigation",
        "title": "Reduce automated traffic",
        "why_it_matters": "Bot activity can distort analytics and degrade UX.",
        "steps": [
            "Add bot challenges on high-risk endpoints.",
            "Rate limit abusive IP ranges.",
            "Block obvious automation signatures.",
            "Review access logs for repeat offenders.",
        ],
        "priority": "P2",
        "effort": "low",
        "expected_effect": "security",
        "evidence_links": evidence,
        "automation_possible": True,
    }


def _action_generic_investigation(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "incident_investigation",
        "title": "Investigate incident impact",
        "why_it_matters": "Fast triage helps restore trust and conversion.",
        "steps": [
            "Review logs and traces during the incident window.",
            "Check for error rate spikes on key endpoints.",
            "Validate critical user journeys end-to-end.",
            "Document findings and mitigation steps.",
        ],
        "priority": "P2",
        "effort": "med",
        "expected_effect": "conversion",
        "evidence_links": evidence,
        "automation_possible": False,
    }


EVENT_TYPE_ACTIONS: dict[str, list[ActionBuilder]] = {
    "credential_stuffing": [_action_credential_stuffing],
    "credential_stuffing_blocked": [_action_credential_stuffing],
    "brute_force": [_action_credential_stuffing],
    "sql_injection_attempt": [_action_sql_injection],
    "xss_attempt": [_action_sql_injection],
    "script_injection_detected": [_action_script_integrity],
    "csp_violation": [_action_csp_hardening],
    "form_tamper": [_action_integrity_audit],
    "bot_surge": [_action_bot_mitigation],
    "headless_browser_detected": [_action_bot_mitigation],
}

CATEGORY_ACTIONS: dict[str, list[ActionBuilder]] = {
    "login": [_action_login_hardening],
    "threat": [_action_threat_review],
    "integrity": [_action_integrity_audit],
    "bot": [_action_bot_mitigation],
    "anomaly": [_action_generic_investigation],
    "mixed": [_action_generic_investigation],
}


def _extract_event_types(incident: Incident) -> list[str]:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    event_counts = evidence.get("event_types") if isinstance(evidence, dict) else None
    if not isinstance(event_counts, dict):
        return []
    return [str(key) for key in event_counts.keys()]


def _extract_paths(incident: Incident) -> list[str]:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    path_counts = evidence.get("request_paths") if isinstance(evidence, dict) else None
    if not isinstance(path_counts, dict):
        return []
    ordered = sorted(path_counts.items(), key=lambda item: int(item[1] or 0), reverse=True)
    paths = []
    for path, _count in ordered:
        if isinstance(path, str):
            paths.append(path)
    return paths


def _build_evidence_links(incident: Incident, impact_estimate: ImpactEstimate | None) -> dict[str, Any]:
    evidence = incident.evidence_json if isinstance(incident.evidence_json, dict) else {}
    event_counts = evidence.get("event_types") if isinstance(evidence, dict) else None
    signal_counts = evidence.get("signal_types") if isinstance(evidence, dict) else None
    path_counts = evidence.get("request_paths") if isinstance(evidence, dict) else None
    links = {
        "paths": _extract_paths(incident),
        "event_counts": event_counts if isinstance(event_counts, dict) else {},
        "signal_counts": signal_counts if isinstance(signal_counts, dict) else {},
        "path_counts": path_counts if isinstance(path_counts, dict) else {},
    }
    if impact_estimate and isinstance(impact_estimate.explanation_json, dict):
        links["impact_summary"] = impact_estimate.explanation_json.get("observed")
    return links


def _form_submit_failure_flag(impact_estimate: ImpactEstimate | None) -> bool:
    if not impact_estimate or not isinstance(impact_estimate.explanation_json, dict):
        return False
    observed = impact_estimate.explanation_json.get("observed") or {}
    baseline = impact_estimate.explanation_json.get("baseline") or {}
    try:
        observed_submit = float(observed.get("submit_rate") or 0.0)
        baseline_submit = float(baseline.get("submit_rate") or 0.0)
        observed_error = float(observed.get("error_rate") or 0.0)
        baseline_error = float(baseline.get("error_rate") or 0.0)
    except (TypeError, ValueError):
        return False
    if baseline_submit > 0 and (baseline_submit - observed_submit) >= 0.05:
        return True
    if baseline_error > 0 and (observed_error - baseline_error) >= 0.05:
        return True
    return False


def _select_actions(
    incident: Incident,
    impact_estimate: ImpactEstimate | None,
    evidence_links: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_actions(builders: list[ActionBuilder]) -> None:
        for builder in builders:
            action = builder(evidence_links)
            action_id = action.get("id")
            if not action_id or action_id in seen_ids:
                continue
            seen_ids.add(action_id)
            actions.append(action)

    for event_type in _extract_event_types(incident):
        builders = EVENT_TYPE_ACTIONS.get(event_type)
        if builders:
            add_actions(builders)

    if _form_submit_failure_flag(impact_estimate):
        add_actions([_action_form_submit_failure])

    category = (incident.category or "").lower()
    if not actions:
        add_actions(CATEGORY_ACTIONS.get(category, []))
    if not actions:
        add_actions([_action_generic_investigation])

    return actions


def generate_prescriptions(
    db: Session,
    *,
    incident: Incident,
    impact_estimate: ImpactEstimate | None = None,
) -> PrescriptionBundle:
    evidence_links = _build_evidence_links(incident, impact_estimate)
    items = _select_actions(incident, impact_estimate, evidence_links)

    bundle = (
        db.query(PrescriptionBundle)
        .filter(PrescriptionBundle.incident_id == incident.id)
        .first()
    )
    if bundle is None:
        bundle = PrescriptionBundle(
            tenant_id=incident.tenant_id,
            website_id=incident.website_id,
            environment_id=incident.environment_id,
            incident_id=incident.id,
            status="suggested",
            items_json=items,
        )
        db.add(bundle)
        db.flush()
    else:
        bundle.items_json = items
        if not bundle.status:
            bundle.status = "suggested"

    existing_items = (
        db.query(PrescriptionItem)
        .filter(
            PrescriptionItem.bundle_id == bundle.id,
            PrescriptionItem.tenant_id == incident.tenant_id,
        )
        .all()
    )
    existing_by_key = {item.key: item for item in existing_items}
    for action in items:
        if not isinstance(action, dict):
            continue
        key = str(action.get("id") or "").strip()
        if not key:
            continue
        evidence_json = action.get("evidence_links")
        record = existing_by_key.get(key)
        if record is None:
            db.add(
                PrescriptionItem(
                    bundle_id=bundle.id,
                    tenant_id=incident.tenant_id,
                    website_id=incident.website_id,
                    environment_id=incident.environment_id,
                    incident_id=incident.id,
                    key=key,
                    title=str(action.get("title") or key),
                    priority=str(action.get("priority") or "P2"),
                    effort=str(action.get("effort") or "med"),
                    expected_effect=str(action.get("expected_effect") or "conversion"),
                    status="suggested",
                    evidence_json=evidence_json if isinstance(evidence_json, dict) else None,
                )
            )
        else:
            record.title = str(action.get("title") or record.title)
            record.priority = str(action.get("priority") or record.priority)
            record.effort = str(action.get("effort") or record.effort)
            record.expected_effect = str(action.get("expected_effect") or record.expected_effect)
            if isinstance(evidence_json, dict):
                record.evidence_json = evidence_json

    incident.prescription_bundle_id = str(bundle.id)
    return bundle
