from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_platform_admin
from app.core.perf import get_recent_request_perf_records
from app.schemas.admin import AdminPerfRequestRecord


router = APIRouter(prefix="/admin/perf", tags=["admin", "perf"])


@router.get("/requests", response_model=list[AdminPerfRequestRecord])
def list_recent_request_perf(
    limit: int = Query(200, ge=1, le=200),
    _current_user=Depends(require_platform_admin()),
):
    return get_recent_request_perf_records(limit=limit)
