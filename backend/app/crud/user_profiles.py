from sqlalchemy.orm import Session

from app.models.user_profiles import UserProfile


def get_or_create_profile(
    db: Session,
    user_id: int,
    *,
    default_display_name: str | None = None,
) -> UserProfile:
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user_id)
        .first()
    )
    if profile:
        return profile
    profile = UserProfile(user_id=user_id, display_name=default_display_name)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    user_id: int,
    changes: dict,
    *,
    default_display_name: str | None = None,
) -> UserProfile:
    profile = get_or_create_profile(db, user_id, default_display_name=default_display_name)
    if "display_name" in changes and changes["display_name"] is not None:
        profile.display_name = changes["display_name"]
    if "avatar_url" in changes and changes["avatar_url"] is not None:
        profile.avatar_url = changes["avatar_url"]
    if "timezone" in changes and changes["timezone"] is not None:
        profile.timezone = changes["timezone"]
    if "email_opt_out" in changes and changes["email_opt_out"] is not None:
        profile.email_opt_out = bool(changes["email_opt_out"])
    db.commit()
    db.refresh(profile)
    return profile
