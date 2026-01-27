from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.incidents import Incident
from app.models.protection_presets import ProtectionPreset
from app.models.websites import Website
from app.models.website_stack_profiles import WebsiteStackProfile


PRESET_TYPE_CSP = "csp"
PRESET_TYPE_RATE_LIMIT = "rate_limit"
PRESET_TYPE_LOCKOUT = "lockout"
PRESET_TYPE_WAF = "waf"

ALL_PRESET_TYPES = {
    PRESET_TYPE_CSP,
    PRESET_TYPE_RATE_LIMIT,
    PRESET_TYPE_LOCKOUT,
    PRESET_TYPE_WAF,
}


def _extract_evidence_dict(incident: Incident) -> dict[str, Any]:
    return incident.evidence_json if isinstance(incident.evidence_json, dict) else {}


def _extract_event_types(incident: Incident) -> set[str]:
    evidence = _extract_evidence_dict(incident)
    bucket = evidence.get("event_types")
    if not isinstance(bucket, dict):
        return set()
    return {str(key).lower() for key in bucket.keys()}


def _extract_paths(incident: Incident) -> list[str]:
    evidence = _extract_evidence_dict(incident)
    paths = evidence.get("request_paths")
    if isinstance(paths, dict):
        return [str(key) for key in paths.keys()]
    return []


def _needs_login_protection(incident: Incident) -> bool:
    event_types = _extract_event_types(incident)
    title = (incident.title or "").lower()
    if incident.category == "login":
        return True
    return any(
        key in event_types
        for key in {"credential_stuffing", "brute_force_login", "login_failure"}
    ) or "login" in title


def _needs_integrity_protection(incident: Incident) -> bool:
    event_types = _extract_event_types(incident)
    title = (incident.title or "").lower()
    if incident.category in {"integrity", "security"}:
        return True
    return any(key in event_types for key in {"csp_violation", "script_injection"}) or "script" in title


def _needs_checkout_protection(incident: Incident) -> bool:
    event_types = _extract_event_types(incident)
    title = (incident.title or "").lower()
    if incident.category in {"conversion", "checkout"}:
        return True
    return any("checkout" in key for key in event_types) or "checkout" in title


def _default_paths(incident: Incident) -> list[str]:
    paths = _extract_paths(incident)
    if paths:
        return sorted({path.strip() for path in paths if path})
    defaults: list[str] = []
    if _needs_login_protection(incident):
        defaults.extend(["/login", "/auth/login"])
    if _needs_checkout_protection(incident):
        defaults.extend(["/checkout", "/cart", "/payment"])
    return defaults or ["/"]


def _build_csp_policy(domain: str | None, report_only: bool) -> tuple[str, dict[str, list[str]]]:
    base_domain = domain or "example.com"
    directives: dict[str, list[str]] = {
        "default-src": ["'self'"],
        "script-src": ["'self'", f"https://{base_domain}", f"https://*.{base_domain}"],
        "style-src": ["'self'", "'unsafe-inline'", f"https://{base_domain}"],
        "img-src": ["'self'", "data:", f"https://{base_domain}", f"https://*.{base_domain}"],
        "connect-src": ["'self'", f"https://{base_domain}", f"https://*.{base_domain}"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "frame-ancestors": ["'none'"],
        "upgrade-insecure-requests": [],
        "report-uri": ["https://your-api-domain/api/v1/ingest/integrity"],
    }
    parts = []
    for key, values in directives.items():
        if not values:
            parts.append(key)
        else:
            parts.append(f"{key} {' '.join(values)}")
    policy = "; ".join(parts)
    header_name = "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
    return f"{header_name}: {policy}", directives


def _csp_preset(*, incident: Incident, website: Website | None, report_only: bool = True) -> dict[str, Any]:
    header_line, directives = _build_csp_policy(getattr(website, "domain", None), report_only)
    nginx_snippet = (
        "add_header Content-Security-Policy-Report-Only "
        f"\"{header_line.split(': ', 1)[1]}\" always;"
    )
    markdown = "\n".join(
        [
            "# CSP preset (report-only)",
            "",
            "Apply as a report-only policy first, then tighten.",
            "",
            "```",
            header_line,
            "```",
            "",
            "```nginx",
            nginx_snippet,
            "```",
        ]
    )
    return {
        "type": PRESET_TYPE_CSP,
        "title": "CSP report-only baseline",
        "summary": "A conservative CSP you can deploy in report-only mode to measure violations.",
        "metadata": {"report_only": report_only},
        "formats": {
            "copy_blocks": [
                {"label": "HTTP header", "content": header_line},
                {"label": "Nginx snippet", "content": nginx_snippet},
            ],
            "json": {
                "mode": "report-only" if report_only else "enforce",
                "header": header_line.split(": ", 1)[0],
                "policy": header_line.split(": ", 1)[1],
                "directives": directives,
            },
            "markdown": markdown,
        },
        "evidence": _extract_evidence_dict(incident),
    }


def _rate_limit_preset(*, incident: Incident) -> dict[str, Any]:
    paths = _default_paths(incident)
    nginx_rules = [
        "limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;",
        "server {",
    ]
    for path in paths:
        nginx_rules.extend(
            [
                f"  location {path} {{",
                "    limit_req zone=auth burst=20 nodelay;",
                "  }",
            ]
        )
    nginx_rules.append("}")
    nginx_snippet = "\n".join(nginx_rules)
    markdown = "\n".join(
        [
            "# Rate limit preset",
            "",
            "Apply per-IP throttling on sensitive routes.",
            "",
            "```nginx",
            nginx_snippet,
            "```",
        ]
    )
    return {
        "type": PRESET_TYPE_RATE_LIMIT,
        "title": "Rate limit sensitive paths",
        "summary": "Throttle login/checkout endpoints to slow automated abuse.",
        "metadata": {"paths": paths, "burst": 20, "rate": "10r/m"},
        "formats": {
            "copy_blocks": [{"label": "Nginx snippet", "content": nginx_snippet}],
            "json": {"paths": paths, "rate": "10r/m", "burst": 20, "scope": "ip"},
            "markdown": markdown,
        },
        "evidence": _extract_evidence_dict(incident),
    }


def _lockout_preset(*, incident: Incident) -> dict[str, Any]:
    config = {
        "window_minutes": 10,
        "max_failures": 8,
        "actions": ["lock_account", "require_mfa"],
    }
    markdown = "\n".join(
        [
            "# Lockout / MFA preset",
            "",
            "Require step-up authentication after repeated failures.",
            "",
            "```json",
            json.dumps(config, indent=2),
            "```",
        ]
    )
    return {
        "type": PRESET_TYPE_LOCKOUT,
        "title": "Account lockout + MFA",
        "summary": "Trigger lockout or MFA after repeated failed logins.",
        "metadata": config,
        "formats": {
            "copy_blocks": [{"label": "App config JSON", "content": json.dumps(config, indent=2)}],
            "json": config,
            "markdown": markdown,
        },
        "evidence": _extract_evidence_dict(incident),
    }


def _waf_preset(*, incident: Incident) -> dict[str, Any]:
    paths = _default_paths(incident)
    primary_path = paths[0] if paths else "/"
    expression = (
        f"(http.request.uri.path contains \"{primary_path}\") and "
        "(http.request.body contains \"' OR\" or http.request.body contains \"<script\")"
    )
    markdown = "\n".join(
        [
            "# WAF rule suggestions",
            "",
            "Use in report-only mode first if supported.",
            "",
            "```",
            expression,
            "```",
        ]
    )
    return {
        "type": PRESET_TYPE_WAF,
        "title": "WAF rule suggestions",
        "summary": "Report-only WAF filters to reduce common injection attempts.",
        "metadata": {"mode": "report-only", "expression": expression, "path": primary_path},
        "formats": {
            "copy_blocks": [{"label": "Cloudflare expression", "content": expression}],
            "json": {"expression": expression, "mode": "report-only"},
            "markdown": markdown,
        },
        "evidence": _extract_evidence_dict(incident),
    }


def _desired_preset_types(incident: Incident) -> list[str]:
    types: list[str] = []
    if _needs_integrity_protection(incident):
        types.extend([PRESET_TYPE_CSP, PRESET_TYPE_WAF])
    if _needs_login_protection(incident):
        types.extend([PRESET_TYPE_RATE_LIMIT, PRESET_TYPE_LOCKOUT, PRESET_TYPE_WAF])
    if _needs_checkout_protection(incident) and PRESET_TYPE_RATE_LIMIT not in types:
        types.append(PRESET_TYPE_RATE_LIMIT)
    if not types:
        types.append(PRESET_TYPE_CSP)
    return list(dict.fromkeys(types))


def _generate_preset_payload(
    preset_type: str,
    *,
    incident: Incident,
    website: Website | None,
) -> dict[str, Any]:
    if preset_type == PRESET_TYPE_CSP:
        return _csp_preset(incident=incident, website=website)
    if preset_type == PRESET_TYPE_RATE_LIMIT:
        return _rate_limit_preset(incident=incident)
    if preset_type == PRESET_TYPE_LOCKOUT:
        return _lockout_preset(incident=incident)
    if preset_type == PRESET_TYPE_WAF:
        return _waf_preset(incident=incident)
    raise ValueError(f"Unknown preset type {preset_type}")


def get_or_generate_presets(
    db: Session,
    *,
    incident: Incident,
    stack_profile: WebsiteStackProfile | None = None,
    website: Website | None = None,
) -> list[ProtectionPreset]:
    existing = (
        db.query(ProtectionPreset)
        .filter(
            ProtectionPreset.tenant_id == incident.tenant_id,
            ProtectionPreset.incident_id == incident.id,
        )
        .all()
    )
    existing_map = {preset.preset_type: preset for preset in existing}
    desired_types = _desired_preset_types(incident)

    presets = list(existing)
    for preset_type in desired_types:
        if preset_type in existing_map:
            continue
        payload = _generate_preset_payload(preset_type, incident=incident, website=website)
        preset = ProtectionPreset(
            tenant_id=incident.tenant_id,
            website_id=incident.website_id,
            incident_id=incident.id,
            preset_type=preset_type,
            content_json=payload,
        )
        db.add(preset)
        db.commit()
        db.refresh(preset)
        presets.append(preset)
    return presets
