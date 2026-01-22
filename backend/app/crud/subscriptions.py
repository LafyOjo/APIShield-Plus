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


def get_latest_subscription_for_tenant(db: Session, tenant_id: int) -> Subscription | None:
    return (
        db.query(Subscription)
        .filter(Subscription.tenant_id == tenant_id)
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
        if plan:
            from app.billing.catalog import plan_key_from_plan_name

            subscription.plan_key = plan_key_from_plan_name(plan.name)
        seed_entitlements_from_plan(db, tenant_id, plan)
        db.commit()
        db.refresh(subscription)
        from app.core.entitlements import invalidate_entitlement_cache

        invalidate_entitlement_cache(tenant_id)
        return subscription
    subscription = Subscription(
        tenant_id=tenant_id,
        plan_id=plan_id,
        plan_key=None,
        status=status,
        current_period_start=now,
    )
    db.add(subscription)
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if plan:
        from app.billing.catalog import plan_key_from_plan_name

        subscription.plan_key = plan_key_from_plan_name(plan.name)
    seed_entitlements_from_plan(db, tenant_id, plan)
    db.commit()
    db.refresh(subscription)
    from app.core.entitlements import invalidate_entitlement_cache

    invalidate_entitlement_cache(tenant_id)
    return subscription


def get_subscription_by_stripe_ids(
    db: Session,
    *,
    stripe_subscription_id: str | None = None,
    stripe_customer_id: str | None = None,
) -> Subscription | None:
    if not stripe_subscription_id and not stripe_customer_id:
        return None
    query = db.query(Subscription)
    if stripe_subscription_id:
        query = query.filter(Subscription.stripe_subscription_id == stripe_subscription_id)
    if stripe_customer_id:
        query = query.filter(Subscription.stripe_customer_id == stripe_customer_id)
    return query.order_by(Subscription.id.desc()).first()


def upsert_stripe_subscription(
    db: Session,
    *,
    tenant_id: int,
    plan: Plan,
    plan_key: str | None,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    status: str,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
    cancel_at_period_end: bool | None = None,
    seats: int | None = None,
) -> Subscription:
    effective_plan = plan
    effective_plan_key = plan_key
    if status not in ACTIVE_STATUSES:
        from app.crud.plans import get_plan_by_name
        from app.billing.catalog import plan_key_from_plan_name

        free_plan = get_plan_by_name(db, "Free")
        if free_plan:
            effective_plan = free_plan
            effective_plan_key = plan_key_from_plan_name(free_plan.name)

    subscription = get_subscription_by_stripe_ids(
        db,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
    )
    if not subscription:
        subscription = get_latest_subscription_for_tenant(db, tenant_id)
    if not subscription:
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            provider="stripe",
            status=status,
        )
        db.add(subscription)

    subscription.plan_id = effective_plan.id
    subscription.plan_key = effective_plan_key
    subscription.provider = "stripe"
    subscription.provider_subscription_id = stripe_subscription_id or subscription.provider_subscription_id
    subscription.stripe_subscription_id = stripe_subscription_id or subscription.stripe_subscription_id
    subscription.stripe_customer_id = stripe_customer_id or subscription.stripe_customer_id
    subscription.status = status
    if current_period_start is not None:
        subscription.current_period_start = current_period_start
    if current_period_end is not None:
        subscription.current_period_end = current_period_end
    if cancel_at_period_end is not None:
        subscription.cancel_at_period_end = cancel_at_period_end
    if seats is not None:
        subscription.seats = seats

    db.commit()
    db.refresh(subscription)
    seed_entitlements_from_plan(db, tenant_id, effective_plan)
    db.commit()
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
