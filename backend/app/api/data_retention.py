from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.core.retention import validate_event_type
from app.crud.data_retention import get_policies, upsert_policy
from app.crud.retention_runs import list_retention_runs
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.data_retention import DataRetentionRead, DataRetentionUpdate
from app.schemas.retention_runs import RetentionRunRead
from app.tenancy.dependencies import require_roles, require_tenant_context


router = APIRouter(tags=["data-retention"])


def _resolve_tenant_id(db, tenant_hint: str) -> int:
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
    return tenant.id


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _build_retention_cutoff(run, *, use_finished: bool = True):
    base_time = run.finished_at if use_finished and run.finished_at else run.started_at
    if not base_time:
        return None, None
    event_cutoff = base_time - timedelta(days=run.event_retention_days)
    raw_ip_cutoff = base_time - timedelta(days=run.raw_ip_retention_days)
    return event_cutoff, raw_ip_cutoff


@router.get("/retention", response_model=list[DataRetentionRead])
def list_retention(
    db=Depends(get_db),
    ctx=Depends(require_tenant_context(user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    return get_policies(db, tenant_id)


@router.patch("/retention", response_model=DataRetentionRead)
def update_retention(
    payload: DataRetentionUpdate,
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    try:
        validate_event_type(payload.event_type)
        return upsert_policy(db, tenant_id, payload.event_type, payload.days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/retention/runs", response_model=list[RetentionRunRead])
def list_retention_run_evidence(
    db=Depends(get_db),
    ctx=Depends(require_roles([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    limit: int = 200,
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    parsed_from = _parse_datetime(from_ts)
    parsed_to = _parse_datetime(to_ts)
    runs = list_retention_runs(db, tenant_id, from_ts=parsed_from, to_ts=parsed_to, limit=limit)
    response = []
    for run in runs:
        event_cutoff, raw_ip_cutoff = _build_retention_cutoff(run)
        response.append(
            RetentionRunRead(
                id=run.id,
                tenant_id=run.tenant_id,
                started_at=run.started_at,
                finished_at=run.finished_at,
                status=run.status,
                event_retention_days=run.event_retention_days,
                raw_ip_retention_days=run.raw_ip_retention_days,
                behaviour_events_deleted=run.behaviour_events_deleted,
                security_events_deleted=run.security_events_deleted,
                alerts_raw_ip_scrubbed=run.alerts_raw_ip_scrubbed,
                events_raw_ip_scrubbed=run.events_raw_ip_scrubbed,
                audit_logs_raw_ip_scrubbed=run.audit_logs_raw_ip_scrubbed,
                security_events_raw_ip_scrubbed=run.security_events_raw_ip_scrubbed,
                error_message=run.error_message,
                event_cutoff=event_cutoff,
                raw_ip_cutoff=raw_ip_cutoff,
            )
        )
    return response
