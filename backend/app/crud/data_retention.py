from sqlalchemy.orm import Session

from app.core.retention import DEFAULT_RETENTION_DAYS, validate_event_type
from app.models.data_retention import DataRetentionPolicy


def create_default_policies(db: Session, tenant_id: int) -> list[DataRetentionPolicy]:
    policies = []
    for event_type, days in DEFAULT_RETENTION_DAYS.items():
        policy = DataRetentionPolicy(
            tenant_id=tenant_id,
            event_type=event_type,
            days=days,
        )
        db.add(policy)
        policies.append(policy)
    db.flush()
    return policies


def get_policies(db: Session, tenant_id: int) -> list[DataRetentionPolicy]:
    return (
        db.query(DataRetentionPolicy)
        .filter(DataRetentionPolicy.tenant_id == tenant_id)
        .order_by(DataRetentionPolicy.event_type)
        .all()
    )


def upsert_policy(db: Session, tenant_id: int, event_type: str, days: int) -> DataRetentionPolicy:
    validate_event_type(event_type)
    if days <= 0:
        raise ValueError("days must be positive")
    policy = (
        db.query(DataRetentionPolicy)
        .filter(
            DataRetentionPolicy.tenant_id == tenant_id,
            DataRetentionPolicy.event_type == event_type,
        )
        .first()
    )
    if policy:
        policy.days = days
    else:
        policy = DataRetentionPolicy(
            tenant_id=tenant_id,
            event_type=event_type,
            days=days,
        )
        db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy
