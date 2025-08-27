# This module defines how we look up or create security policies
# that can be attached to users. Policies control things like
# login limits, MFA, and geo-fencing for extra protection.

from sqlalchemy.orm import Session
from app.models.policies import Policy
from app.models.users import User

# Simple helper to fetch a Policy object by its ID. If no row
# exists with that primary key, it quietly returns None.
def get_policy_by_id(db: Session, policy_id: int) -> Policy | None:
    return db.query(Policy).filter(Policy.id == policy_id).first()


# Create and persist a new Policy row in the database. You can
# pass in the max failed attempts and optional flags like MFA
# or geo-fencing. It commits immediately and returns the row.
def create_policy(
    db: Session,
    *,
    failed_attempts_limit: int,
    mfa_required: bool = False,
    geo_fencing_enabled: bool = False,
) -> Policy:
    policy = Policy(
        failed_attempts_limit=failed_attempts_limit,
        mfa_required=mfa_required,
        geo_fencing_enabled=geo_fencing_enabled,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


# Given a User, look up their attached policy. If they don’t
# have one set (policy_id is None), return None. Otherwise
# delegate to get_policy_by_id for the actual DB fetch.
def get_policy_for_user(db: Session, user: User) -> Policy | None:
    if user.policy_id is None:
        return None
    return get_policy_by_id(db, user.policy_id)
