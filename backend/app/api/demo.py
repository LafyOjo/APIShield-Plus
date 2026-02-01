from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.jobs.seed_demo_data import seed_demo_data
from app.models.enums import RoleEnum
from app.schemas.demo import DemoSeedRequest, DemoSeedResponse
from app.tenancy.dependencies import require_role_in_tenant


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", response_model=DemoSeedResponse, status_code=status.HTTP_201_CREATED)
def seed_demo(
    payload: DemoSeedRequest,
    db: Session = Depends(get_db),
    ctx=Depends(require_role_in_tenant([RoleEnum.OWNER, RoleEnum.ADMIN], user_resolver=get_current_user)),
):
    if settings.LAUNCH_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo seeding is disabled in launch mode",
        )
    try:
        result = seed_demo_data(
            db,
            tenant_id=ctx.tenant_id,
            created_by_user_id=ctx.user_id,
            force=payload.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return DemoSeedResponse(
        tenant_id=result.tenant_id,
        seeded_at=result.seeded_at,
        expires_at=result.expires_at,
        counts=result.counts,
        demo_enabled=True,
        message="Demo data ready",
    )
