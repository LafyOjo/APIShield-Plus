from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.crud.user_profiles import get_or_create_profile, update_profile
from app.schemas.user_profiles import UserProfileRead, UserProfileUpdate


router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=UserProfileRead)
def read_profile(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_or_create_profile(db, current_user.id, default_display_name=current_user.username)


@router.patch("/profile", response_model=UserProfileRead)
def patch_profile(
    payload: UserProfileUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    changes = payload.dict(exclude_unset=True)
    return update_profile(
        db,
        current_user.id,
        changes,
        default_display_name=current_user.username,
    )
