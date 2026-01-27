from sqlalchemy.orm import Session

from app.core.retention import (
    ALLOWED_RETENTION_DATASETS,
    default_dataset_retention_days,
    validate_dataset_key,
)
from app.models.tenant_retention_policies import TenantRetentionPolicy


def create_default_dataset_policies(
    db: Session,
    tenant_id: int,
    *,
    plan_limits: dict | None = None,
) -> list[TenantRetentionPolicy]:
    policies: list[TenantRetentionPolicy] = []
    for dataset_key in sorted(ALLOWED_RETENTION_DATASETS):
        policy = TenantRetentionPolicy(
            tenant_id=tenant_id,
            dataset_key=dataset_key,
            retention_days=default_dataset_retention_days(dataset_key, plan_limits=plan_limits),
        )
        db.add(policy)
        policies.append(policy)
    db.flush()
    return policies


def get_policies(
    db: Session,
    tenant_id: int,
    *,
    ensure_defaults: bool = False,
    plan_limits: dict | None = None,
) -> list[TenantRetentionPolicy]:
    policies = (
        db.query(TenantRetentionPolicy)
        .filter(TenantRetentionPolicy.tenant_id == tenant_id)
        .order_by(TenantRetentionPolicy.dataset_key)
        .all()
    )
    if policies or not ensure_defaults:
        return policies
    created = create_default_dataset_policies(db, tenant_id, plan_limits=plan_limits)
    db.commit()
    return created


def upsert_policy(
    db: Session,
    tenant_id: int,
    dataset_key: str,
    *,
    retention_days: int | None = None,
    is_legal_hold_enabled: bool | None = None,
    legal_hold_reason: str | None = None,
    updated_by_user_id: int | None = None,
) -> TenantRetentionPolicy:
    validate_dataset_key(dataset_key)
    policy = (
        db.query(TenantRetentionPolicy)
        .filter(
            TenantRetentionPolicy.tenant_id == tenant_id,
            TenantRetentionPolicy.dataset_key == dataset_key,
        )
        .first()
    )
    if not policy:
        retention_value = (
            retention_days
            if retention_days is not None
            else default_dataset_retention_days(dataset_key)
        )
        policy = TenantRetentionPolicy(
            tenant_id=tenant_id,
            dataset_key=dataset_key,
            retention_days=retention_value,
        )
        db.add(policy)
    if retention_days is not None:
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        policy.retention_days = retention_days
    if is_legal_hold_enabled is not None:
        if is_legal_hold_enabled:
            if not legal_hold_reason or not legal_hold_reason.strip():
                raise ValueError("legal_hold_reason is required when enabling a legal hold")
            policy.enable_legal_hold(legal_hold_reason.strip())
        else:
            policy.disable_legal_hold()
    if updated_by_user_id is not None:
        policy.updated_by_user_id = updated_by_user_id
    db.commit()
    db.refresh(policy)
    return policy
