from datetime import datetime, timezone

from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.data_retention import create_default_policies
from app.crud.tenant_settings import create_default_settings
from app.crud.feature_entitlements import seed_entitlements_from_plan
from app.crud.plans import get_plan_by_name
from app.core.entitlements import validate_feature
from app.core.time import utcnow
from app.core.utils.slug import ensure_unique_slug, slugify
from app.models.audit_logs import AuditLog
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.feature_entitlements import FeatureEntitlement
from app.models.memberships import Membership
from app.models.plans import Plan
from app.models.subscriptions import Subscription
from app.models.tenants import Tenant
from app.models.users import User


def create_tenant(
    db: Session,
    name: str,
    slug: str | None = None,
    created_by_user_id: int | None = None,
) -> Tenant:
    base_slug = slugify(slug or name)
    unique_slug = ensure_unique_slug(db, base_slug)
    tenant = Tenant(name=name, slug=unique_slug, created_by_user_id=created_by_user_id)
    db.add(tenant)
    db.flush()
    default_plan = get_plan_by_name(db, "Free")
    raw_ip_retention_days = None
    if default_plan:
        limit_value = (default_plan.limits_json or {}).get("raw_ip_retention_days")
        if isinstance(limit_value, int) and limit_value > 0:
            raw_ip_retention_days = limit_value
    create_default_settings(db, tenant.id, raw_ip_retention_days=raw_ip_retention_days)
    create_default_policies(db, tenant.id)
    seed_entitlements_from_plan(db, tenant.id, default_plan)
    try:
        db.commit()
        db.refresh(tenant)
        return tenant
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Tenant slug already exists.") from exc


def provision_tenant_defaults(
    db: Session,
    *,
    tenant: Tenant,
    owner_user: User,
    plan: Plan,
) -> Membership:
    membership = Membership(
        tenant_id=tenant.id,
        user_id=owner_user.id,
        role=RoleEnum.OWNER,
        status=MembershipStatusEnum.ACTIVE,
        created_by_user_id=owner_user.id,
    )
    db.add(membership)
    raw_ip_retention_days = None
    if plan:
        limit_value = (plan.limits_json or {}).get("raw_ip_retention_days")
        if isinstance(limit_value, int) and limit_value > 0:
            raw_ip_retention_days = limit_value
    create_default_settings(db, tenant.id, raw_ip_retention_days=raw_ip_retention_days)
    create_default_policies(db, tenant.id)
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="active",
            current_period_start=utcnow(),
        )
    )
    for feature, enabled in (plan.features_json or {}).items():
        try:
            validate_feature(feature)
        except ValueError:
            continue
        db.add(
            FeatureEntitlement(
                tenant_id=tenant.id,
                feature=feature,
                enabled=bool(enabled),
                source="plan",
                source_plan_id=plan.id,
            )
        )
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            username=owner_user.username,
            event="tenant_created",
        )
    )
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            username=owner_user.username,
            event="owner_membership_created",
        )
    )
    return membership


def create_tenant_with_owner(
    db: Session,
    *,
    name: str,
    slug: str | None,
    owner_user: User,
    plan: Plan | None = None,
) -> tuple[Tenant, Membership]:
    plan = plan or get_plan_by_name(db, "Free")
    if plan is None:
        raise ValueError("Default plan not configured.")
    base_slug = slugify(slug or name)
    unique_slug = ensure_unique_slug(db, base_slug)
    tenant = Tenant(
        name=name,
        slug=unique_slug,
        created_by_user_id=owner_user.id,
    )
    db.add(tenant)
    db.flush()
    membership = provision_tenant_defaults(db, tenant=tenant, owner_user=owner_user, plan=plan)
    return tenant, membership


def list_tenants_for_user(db: Session, user_id: int) -> list[tuple[Tenant, RoleEnum]]:
    owner_first = case((Membership.role == RoleEnum.OWNER, 0), else_=1)
    return (
        db.query(Tenant, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .filter(
            Membership.user_id == user_id,
            Membership.status == MembershipStatusEnum.ACTIVE,
            Tenant.deleted_at.is_(None),
        )
        .order_by(owner_first, Tenant.name.asc())
        .all()
    )


def _tenant_query(db: Session, *, include_deleted: bool = False):
    query = db.query(Tenant)
    if not include_deleted:
        query = query.filter(Tenant.deleted_at.is_(None))
    return query


def list_tenants(db: Session, *, include_deleted: bool = False) -> list[Tenant]:
    return _tenant_query(db, include_deleted=include_deleted).order_by(Tenant.id).all()


def get_tenant_by_id(
    db: Session,
    tenant_id: int,
    *,
    include_deleted: bool = False,
) -> Tenant | None:
    return _tenant_query(db, include_deleted=include_deleted).filter(Tenant.id == tenant_id).first()


def get_tenant_by_slug(
    db: Session,
    slug: str,
    *,
    include_deleted: bool = False,
) -> Tenant | None:
    return _tenant_query(db, include_deleted=include_deleted).filter(Tenant.slug == slug).first()


def update_tenant(db: Session, tenant_id: int, *, name: str | None = None) -> Tenant | None:
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    if name is not None:
        tenant.name = name
    db.commit()
    db.refresh(tenant)
    return tenant


def soft_delete_tenant(db: Session, tenant_id: int) -> Tenant | None:
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        return None
    tenant.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tenant)
    return tenant


def restore_tenant(db: Session, tenant_id: int) -> Tenant | None:
    tenant = get_tenant_by_id(db, tenant_id, include_deleted=True)
    if not tenant:
        return None
    if tenant.deleted_at is None:
        return tenant
    tenant.deleted_at = None
    db.commit()
    db.refresh(tenant)
    return tenant
