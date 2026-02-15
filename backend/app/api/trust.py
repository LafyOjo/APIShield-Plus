from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.cache import build_cache_key, cache_get, cache_set, db_scope_id
from app.core.config import settings
from app.core.db import get_db
from app.models.enums import RoleEnum
from app.models.trust_scoring import TrustSnapshot
from app.models.tenants import Tenant
from app.schemas.trust import TrustSnapshotRead
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/trust", tags=["trust"])


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_tenant(db: Session, tenant_hint: str) -> Tenant:
    tenant_value = (tenant_hint or "").strip()
    tenant = (
        db.query(Tenant).filter(Tenant.id == int(tenant_value)).first()
        if tenant_value.isdigit()
        else db.query(Tenant).filter(Tenant.slug == tenant_value).first()
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/snapshots", response_model=list[TrustSnapshotRead])
def list_trust_snapshots(
    from_ts: datetime | None = Query(None, alias="from"),
    to_ts: datetime | None = Query(None, alias="to"),
    website_id: int | None = None,
    env_id: int | None = None,
    path: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    include_demo: bool = Query(False, alias="include_demo"),
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    tenant = _resolve_tenant(db, ctx.tenant_id)
    include_demo = bool(include_demo and tenant.is_demo_mode and not settings.LAUNCH_MODE)
    from_ts = _normalize_ts(from_ts)
    to_ts = _normalize_ts(to_ts)
    cache_key = build_cache_key(
        "trust.snapshots",
        tenant_id=tenant.id,
        db_scope=db_scope_id(db),
        filters={
            "from": from_ts,
            "to": to_ts,
            "website_id": website_id,
            "env_id": env_id,
            "path": path,
            "limit": limit,
            "include_demo": include_demo,
        },
    )
    cached = cache_get(cache_key, cache_name="trust.snapshots")
    if cached is not None:
        return cached

    query = db.query(TrustSnapshot).filter(TrustSnapshot.tenant_id == tenant.id)
    if not include_demo:
        query = query.filter(TrustSnapshot.is_demo.is_(False))
    if website_id is not None:
        query = query.filter(TrustSnapshot.website_id == website_id)
    if env_id is not None:
        query = query.filter(TrustSnapshot.environment_id == env_id)
    if path:
        query = query.filter(TrustSnapshot.path == path)
    if from_ts:
        query = query.filter(TrustSnapshot.bucket_start >= from_ts)
    if to_ts:
        query = query.filter(TrustSnapshot.bucket_start <= to_ts)
    rows = query.order_by(TrustSnapshot.bucket_start.asc()).limit(limit).all()
    payload = [TrustSnapshotRead.model_validate(row, from_attributes=True) for row in rows]
    cache_set(
        cache_key,
        payload,
        ttl=settings.CACHE_TTL_TRUST_SNAPSHOTS,
        cache_name="trust.snapshots",
    )
    return payload
