from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.user_tours import get_or_create_tour_state, update_tour_state
from app.models.enums import RoleEnum
from app.schemas.tours import UserTourStateRead, UserTourUpdate
from app.tenancy.dependencies import get_current_membership, require_role_in_tenant


router = APIRouter(prefix="/users/tours", tags=["tours"])


def _serialize_state(state) -> UserTourStateRead:
    return UserTourStateRead(
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        tours_completed=state.tours_completed_json or [],
        tours_dismissed=state.tours_dismissed_json or [],
        last_updated_at=state.last_updated_at,
    )


@router.get("", response_model=UserTourStateRead)
def get_tour_state(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    state = get_or_create_tour_state(db, user_id=membership.user_id, tenant_id=membership.tenant_id)
    return _serialize_state(state)


@router.post("", response_model=UserTourStateRead)
def update_tour_state_endpoint(
    payload: UserTourUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    ctx=Depends(require_role_in_tenant([RoleEnum.VIEWER], user_resolver=get_current_user)),
):
    membership = get_current_membership(db, current_user, ctx.tenant_id)
    state = get_or_create_tour_state(db, user_id=membership.user_id, tenant_id=membership.tenant_id)
    update_tour_state(
        state,
        complete=payload.complete,
        dismiss=payload.dismiss,
        reset=payload.reset,
    )
    db.commit()
    db.refresh(state)
    return _serialize_state(state)
