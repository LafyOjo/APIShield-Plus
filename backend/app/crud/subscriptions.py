from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from app.models.subscriptions import Subscription
from app.models.plans import Plan
from app.crud.feature_entitlements import seed_entitlements_from_plan

ACTIVE_STATUSES = {"active", "trialing", "past_due"}


def get_active_subscription_for_tenant(db: Session, tenant_id: int) -> Subscription | None:
    return (
        db.query(Subscription)
        .options(selectinload(Subscription.plan))
        .filter(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Subscription.id.desc())
        .first()
    )


def set_tenant_plan(
    db: Session,
    tenant_id: int,
    plan_id: int,
    status: str = "active",
) -> Subscription:
    subscription = (
        db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    )
    now = datetime.now(timezone.utc)
    if subscription:
        subscription.plan_id = plan_id
        subscription.status = status
        subscription.current_period_start = now
        plan = db.query(Plan).filter(Plan.id == plan_id).first()
        seed_entitlements_from_plan(db, tenant_id, plan)
        db.commit()
        db.refresh(subscription)
        from app.core.entitlements import invalidate_entitlement_cache

        invalidate_entitlement_cache(tenant_id)
        return subscription
    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        status=status,
        current_period_start=now,
    )
    db.add(subscription)
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    seed_entitlements_from_plan(db, tenant_id, plan)
    db.commit()
    db.refresh(subscription)
    from app.core.entitlements import invalidate_entitlement_cache

    invalidate_entitlement_cache(tenant_id)
    return subscription


def cancel_subscription_stub(
    db: Session,
    subscription_id: int,
    *,
    cancel_at_period_end: bool = True,
) -> Subscription | None:
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not subscription:
        return None
    subscription.cancel_at_period_end = cancel_at_period_end
    subscription.status = "canceled"
    subscription.current_period_end = datetime.now(timezone.utc)
    db.commit()
    db.refresh(subscription)
    from app.core.entitlements import invalidate_entitlement_cache

    invalidate_entitlement_cache(subscription.tenant_id)
    return subscription
