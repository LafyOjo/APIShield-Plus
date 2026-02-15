from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.cache import (
    build_cache_key,
    cache_delete,
    cache_get,
    cache_set,
    db_scope_id,
    invalidate_tenant_cache,
)
from app.core.config import settings
from app.core.db import get_db
from app.core.entitlements import resolve_effective_entitlements
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.crud.website_stack_profiles import get_stack_profile
from app.models.tenants import Tenant
from app.models.websites import Website
from app.presets.generator import get_or_generate_presets
from app.playbooks.generator import get_or_generate_playbook
from app.reports.incident_report import assemble_incident_report, build_incident_report_csv
from app.models.enums import RoleEnum
from app.models.incidents import Incident, IncidentRecovery
from app.models.prescriptions import PrescriptionBundle, PrescriptionItem
from app.models.revenue_impact import ImpactEstimate
from app.models.verification_runs import VerificationCheckRun
from app.insights.prescriptions import generate_prescriptions
from app.schemas.incidents import (
    ImpactEstimateDetail,
    ImpactSummary,
    IncidentListItem,
    IncidentRead,
    IncidentUpdate,
    PrescriptionBundleRead,
    IncidentRecoveryRead,
)
from app.schemas.playbooks import RemediationPlaybookRead
from app.schemas.presets import ProtectionPresetRead
from app.schemas.verification import VerificationCheckRunRead
from app.schemas.prescriptions import PrescriptionItemRead
from app.tenancy.dependencies import require_role_in_tenant
from app.verify.evaluator import evaluate_verification


router = APIRouter(prefix="/incidents", tags=["incidents"])

ALLOWED_STATUSES = {"open", "investigating", "mitigated", "resolved"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_severity(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in ALLOWED_SEVERITIES else None


def _build_map_link_params(incident: Incident) -> dict | None:
    if not incident.first_seen_at or not incident.last_seen_at:
        return None
    params: dict[str, str] = {
        "from": incident.first_seen_at.isoformat(),
        "to": incident.last_seen_at.isoformat(),
    }
    if incident.website_id is not None:
        params["website_id"] = str(incident.website_id)
    if incident.environment_id is not None:
        params["env_id"] = str(incident.environment_id)
    if incident.category:
        params["category"] = incident.category
    if incident.severity:
        params["severity"] = incident.severity
    if incident.primary_ip_hash:
        params["ip_hash"] = incident.primary_ip_hash
    if incident.primary_country_code:
        params["country_code"] = incident.primary_country_code
    return params


def _resolve_tenant(db: Session, tenant_hint: str) -> Tenant:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    return _resolve_tenant(db, tenant_hint).id


def _incident_detail_cache_key(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
    include_demo: bool,
) -> str:
    return build_cache_key(
        "incidents.detail",
        tenant_id=tenant_id,
        db_scope=db_scope_id(db),
        filters={
            "incident_id": incident_id,
            "include_demo": include_demo,
        },
    )


def _clear_incident_detail_cache(db: Session, *, tenant_id: int, incident_id: int) -> None:
    cache_delete(
        _incident_detail_cache_key(
            db,
            tenant_id=tenant_id,
            incident_id=incident_id,
            include_demo=False,
        )
    )
    cache_delete(
        _incident_detail_cache_key(
            db,
            tenant_id=tenant_id,
            incident_id=incident_id,
            include_demo=True,
        )
    )


def _get_incident_or_404(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
    include_demo: bool,
) -> Incident:
    incident = (
        db.query(Incident)
        .filter(Incident.id == incident_id, Incident.tenant_id == tenant_id)
        .first()
    )
    if not incident or (incident.is_demo and not include_demo):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("/", response_model=list[IncidentListItem])
def list_incidents(
    status_value: str | None = Query(None, alias="status"),
    category: str | None = None,
    severity: str | None = None,
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    query = db.query(Incident).filter(Incident.tenant_id == tenant_id)
    if not include_demo:
        query = query.filter(Incident.is_demo.is_(False))
    if status_value:
        query = query.filter(Incident.status == status_value)
    if category:
        query = query.filter(Incident.category == category)
    normalized_severity = _normalize_severity(severity)
    if normalized_severity:
        query = query.filter(Incident.severity == normalized_severity)
    if website_id:
        query = query.filter(Incident.website_id == website_id)
    if env_id:
        query = query.filter(Incident.environment_id == env_id)
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    if from_ts:
        query = query.filter(Incident.last_seen_at >= from_ts)
    if to_ts:
        query = query.filter(Incident.first_seen_at <= to_ts)

    cache_key = build_cache_key(
        "incidents.list",
        tenant_id=tenant_id,
        db_scope=db_scope_id(db),
        filters={
            "status": status_value,
            "category": category,
            "severity": normalized_severity,
            "from": from_ts,
            "to": to_ts,
            "website_id": website_id,
            "env_id": env_id,
            "limit": limit,
            "offset": offset,
            "include_demo": include_demo,
        },
    )
    cached = cache_get(cache_key, cache_name="incidents.list")
    if cached is not None:
        return cached

    rows = query.order_by(Incident.last_seen_at.desc()).offset(offset).limit(limit).all()

    impact_ids = [row.impact_estimate_id for row in rows if row.impact_estimate_id]
    impact_map: dict[int, ImpactEstimate] = {}
    if impact_ids:
        impacts = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.tenant_id == tenant_id,
                ImpactEstimate.id.in_(impact_ids),
            )
            .all()
        )
        impact_map = {impact.id: impact for impact in impacts}

    items: list[IncidentListItem] = []
    for row in rows:
        impact_summary = None
        impact = impact_map.get(row.impact_estimate_id)
        if impact:
            impact_summary = ImpactSummary(
                estimated_lost_revenue=impact.estimated_lost_revenue,
                estimated_lost_conversions=impact.estimated_lost_conversions,
                confidence=impact.confidence,
            )
        items.append(
            IncidentListItem(
                id=row.id,
                status=row.status,
                category=row.category,
                title=row.title,
                severity=row.severity,
                first_seen_at=row.first_seen_at,
                last_seen_at=row.last_seen_at,
                website_id=row.website_id,
                environment_id=row.environment_id,
                impact_estimate_id=row.impact_estimate_id,
                primary_country_code=row.primary_country_code,
                impact_summary=impact_summary,
            )
        )
    cache_set(
        cache_key,
        items,
        ttl=settings.CACHE_TTL_INCIDENTS_LIST,
        cache_name="incidents.list",
    )
    return items


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(
    incident_id: int,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    cache_key = _incident_detail_cache_key(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )
    cached = cache_get(cache_key, cache_name="incidents.detail")
    if cached is not None:
        return IncidentRead(**cached)

    incident = _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )

    impact_estimate = None
    if incident.impact_estimate_id:
        impact = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.id == incident.impact_estimate_id,
                ImpactEstimate.tenant_id == tenant_id,
            )
            .first()
        )
        if impact:
            impact_estimate = ImpactEstimateDetail(
                id=impact.id,
                metric_key=impact.metric_key,
                window_start=impact.window_start,
                window_end=impact.window_end,
                observed_rate=impact.observed_rate,
                baseline_rate=impact.baseline_rate,
                delta_rate=impact.delta_rate,
                estimated_lost_conversions=impact.estimated_lost_conversions,
                estimated_lost_revenue=impact.estimated_lost_revenue,
                confidence=impact.confidence,
                explanation_json=impact.explanation_json,
                created_at=impact.created_at,
            )

    bundle_read = None
    raw_prescriptions = None
    bundle = (
        db.query(PrescriptionBundle)
        .filter(
            PrescriptionBundle.incident_id == incident.id,
            PrescriptionBundle.tenant_id == tenant_id,
        )
        .first()
    )
    if bundle:
        template_map = {}
        raw_items = bundle.items_json if isinstance(bundle.items_json, list) else []
        raw_prescriptions = raw_items
        for raw in raw_items:
            if isinstance(raw, dict) and raw.get("id"):
                template_map[str(raw.get("id"))] = raw
        items = (
            db.query(PrescriptionItem)
            .filter(
                PrescriptionItem.bundle_id == bundle.id,
                PrescriptionItem.tenant_id == tenant_id,
            )
            .order_by(PrescriptionItem.id.asc())
            .all()
        )
        item_payload = [
            PrescriptionItemRead(
                id=item.id,
                bundle_id=item.bundle_id,
                incident_id=item.incident_id,
                key=item.key,
                title=item.title,
                priority=item.priority,
                effort=item.effort,
                expected_effect=item.expected_effect,
                why_it_matters=template_map.get(item.key, {}).get("why_it_matters"),
                steps=template_map.get(item.key, {}).get("steps"),
                status=item.status,
                applied_at=item.applied_at,
                dismissed_at=item.dismissed_at,
                snoozed_until=item.snoozed_until,
                notes=item.notes,
                applied_by_user_id=item.applied_by_user_id,
                evidence_json=item.evidence_json,
                automation_possible=template_map.get(item.key, {}).get("automation_possible"),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
        bundle_read = PrescriptionBundleRead(
            id=bundle.id,
            status=bundle.status,
            created_at=bundle.created_at,
            items=item_payload,
            notes=bundle.notes,
        )

    recovery_read = None
    recovery = (
        db.query(IncidentRecovery)
        .filter(
            IncidentRecovery.incident_id == incident.id,
            IncidentRecovery.tenant_id == tenant_id,
        )
        .order_by(IncidentRecovery.measured_at.desc())
        .first()
    )
    if recovery:
        recovery_read = IncidentRecoveryRead(
            id=recovery.id,
            measured_at=recovery.measured_at,
            window_start=recovery.window_start,
            window_end=recovery.window_end,
            post_conversion_rate=recovery.post_conversion_rate,
            change_in_errors=recovery.change_in_errors,
            change_in_threats=recovery.change_in_threats,
            recovery_ratio=recovery.recovery_ratio,
            confidence=recovery.confidence,
            evidence_json=recovery.evidence_json,
        )

    stack_profile = None
    if incident.website_id is not None:
        stack_profile = get_stack_profile(db, tenant_id=tenant_id, website_id=incident.website_id)
    website = None
    if incident.website_id is not None:
        website = (
            db.query(Website)
            .filter(Website.id == incident.website_id, Website.tenant_id == tenant_id)
            .first()
        )
    playbook = get_or_generate_playbook(
        db,
        incident=incident,
        stack_profile=stack_profile,
        prescriptions=raw_prescriptions,
    )
    playbook_read = None
    if playbook:
        playbook_read = RemediationPlaybookRead(
            id=playbook.id,
            incident_id=playbook.incident_id,
            website_id=playbook.website_id,
            environment_id=playbook.environment_id,
            stack_type=playbook.stack_type,
            status=playbook.status,
            version=playbook.version,
            sections=playbook.sections_json if isinstance(playbook.sections_json, list) else [],
            created_at=playbook.created_at,
            updated_at=playbook.updated_at,
        )

    presets = get_or_generate_presets(
        db,
        incident=incident,
        stack_profile=stack_profile,
        website=website,
    )
    preset_payload = [
        ProtectionPresetRead(
            id=preset.id,
            incident_id=preset.incident_id,
            website_id=preset.website_id,
            preset_type=preset.preset_type,
            content_json=preset.content_json if isinstance(preset.content_json, dict) else {},
            created_at=preset.created_at,
            updated_at=preset.updated_at,
        )
        for preset in presets
    ]

    payload = IncidentRead(
        id=incident.id,
        status=incident.status,
        category=incident.category,
        title=incident.title,
        severity=incident.severity,
        first_seen_at=incident.first_seen_at,
        last_seen_at=incident.last_seen_at,
        website_id=incident.website_id,
        environment_id=incident.environment_id,
        impact_estimate_id=incident.impact_estimate_id,
        primary_country_code=incident.primary_country_code,
        impact_summary=None,
        summary=incident.summary,
        notes=incident.notes,
        primary_ip_hash=incident.primary_ip_hash,
        evidence_json=incident.evidence_json,
        evidence_summary=incident.evidence_json,
        prescription_bundle_id=incident.prescription_bundle_id,
        assigned_to_user_id=incident.assigned_to_user_id,
        impact_estimate=impact_estimate,
        recovery_measurement=recovery_read,
        prescription_bundle=bundle_read,
        remediation_playbook=playbook_read,
        protection_presets=preset_payload,
        map_link_params=_build_map_link_params(incident),
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )
    cache_set(
        cache_key,
        payload,
        ttl=settings.CACHE_TTL_INCIDENT_DETAIL,
        cache_name="incidents.detail",
    )
    return payload


@router.post("/{incident_id}/prescriptions/generate", response_model=PrescriptionBundleRead)
def generate_incident_prescriptions(
    incident_id: int,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ANALYST, RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    incident = _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )

    impact = None
    if incident.impact_estimate_id:
        impact = (
            db.query(ImpactEstimate)
            .filter(
                ImpactEstimate.id == incident.impact_estimate_id,
                ImpactEstimate.tenant_id == tenant_id,
            )
            .first()
        )
    bundle = generate_prescriptions(db, incident=incident, impact_estimate=impact)
    db.commit()

    template_map = {}
    raw_items = bundle.items_json if isinstance(bundle.items_json, list) else []
    for raw in raw_items:
        if isinstance(raw, dict) and raw.get("id"):
            template_map[str(raw.get("id"))] = raw
    items = (
        db.query(PrescriptionItem)
        .filter(
            PrescriptionItem.bundle_id == bundle.id,
            PrescriptionItem.tenant_id == tenant_id,
        )
        .order_by(PrescriptionItem.id.asc())
        .all()
    )
    item_payload = [
        PrescriptionItemRead(
            id=item.id,
            bundle_id=item.bundle_id,
            incident_id=item.incident_id,
            key=item.key,
            title=item.title,
            priority=item.priority,
            effort=item.effort,
            expected_effect=item.expected_effect,
            why_it_matters=template_map.get(item.key, {}).get("why_it_matters"),
            steps=template_map.get(item.key, {}).get("steps"),
            status=item.status,
            applied_at=item.applied_at,
            dismissed_at=item.dismissed_at,
            snoozed_until=item.snoozed_until,
            notes=item.notes,
            applied_by_user_id=item.applied_by_user_id,
            evidence_json=item.evidence_json,
            automation_possible=template_map.get(item.key, {}).get("automation_possible"),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]
    _clear_incident_detail_cache(db, tenant_id=tenant_id, incident_id=incident_id)
    return PrescriptionBundleRead(
        id=bundle.id,
        status=bundle.status,
        created_at=bundle.created_at,
        items=item_payload,
        notes=bundle.notes,
    )


@router.patch("/{incident_id}", response_model=IncidentRead)
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    incident = _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )

    changes = payload.dict(exclude_unset=True)
    status_value = changes.get("status")
    if status_value and status_value not in ALLOWED_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")

    for field, value in changes.items():
        setattr(incident, field, value)
    if "status" in changes:
        incident.status_manual = True

    db.commit()
    db.refresh(incident)
    _clear_incident_detail_cache(db, tenant_id=tenant_id, incident_id=incident_id)
    if "status" in changes:
        invalidate_tenant_cache(tenant_id)
    return incident


@router.get("/{incident_id}/report")
def export_incident_report(
    incident_id: int,
    format_value: str = Query("json", alias="format"),
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    incident = _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )

    report_format = (format_value or "json").strip().lower()
    if report_format not in {"json", "csv"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid report format")

    entitlements = resolve_effective_entitlements(db, tenant_id)
    report = assemble_incident_report(db, incident=incident, entitlements=entitlements)

    if report_format == "csv":
        csv_body = build_incident_report_csv(report)
        filename = f"incident-{incident_id}-report.csv"
        return Response(
            content=csv_body,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return report


@router.get("/{incident_id}/verification", response_model=list[VerificationCheckRunRead])
def list_verification_runs(
    incident_id: int,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )
    runs = (
        db.query(VerificationCheckRun)
        .filter(
            VerificationCheckRun.tenant_id == tenant_id,
            VerificationCheckRun.incident_id == incident_id,
        )
        .order_by(VerificationCheckRun.created_at.desc())
        .all()
    )
    return [
        VerificationCheckRunRead(
            id=run.id,
            incident_id=run.incident_id,
            website_id=run.website_id,
            environment_id=run.environment_id,
            status=run.status,
            checks=run.checks_json if isinstance(run.checks_json, list) else [],
            notes=run.notes,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        for run in runs
    ]


@router.post("/{incident_id}/verification", response_model=VerificationCheckRunRead)
def run_verification(
    incident_id: int,
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.ANALYST, RoleEnum.ADMIN, RoleEnum.OWNER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    tenant_id = tenant.id
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    incident = _get_incident_or_404(
        db,
        tenant_id=tenant_id,
        incident_id=incident_id,
        include_demo=include_demo,
    )

    run = evaluate_verification(db, incident=incident)
    _clear_incident_detail_cache(db, tenant_id=tenant_id, incident_id=incident_id)
    return VerificationCheckRunRead(
        id=run.id,
        incident_id=run.incident_id,
        website_id=run.website_id,
        environment_id=run.environment_id,
        status=run.status,
        checks=run.checks_json if isinstance(run.checks_json, list) else [],
        notes=run.notes,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
