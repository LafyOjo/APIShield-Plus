from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.billing.catalog import get_plan_name, get_price_id, normalize_plan_key, plan_key_from_price_id
from app.core.config import settings
from app.core.referrals import process_referral_conversion
from app.core.affiliates import process_affiliate_conversion, void_affiliate_commission
from app.core.db import get_db
from app.crud.plans import get_plan_by_name
from app.crud.subscriptions import (
    get_latest_subscription_for_tenant,
    get_subscription_by_stripe_ids,
    upsert_stripe_subscription,
)
from app.crud.audit import create_audit_log
from app.crud.tenants import get_tenant_by_id, get_tenant_by_slug
from app.models.enums import RoleEnum
from app.schemas.billing import CheckoutSessionCreate, CheckoutSessionResponse, PortalSessionResponse
from app.tenancy.dependencies import require_role_in_tenant

import stripe


router = APIRouter(prefix="/billing", tags=["billing"])

ALLOWED_STATUSES = {
    "active",
    "trialing",
    "past_due",
    "canceled",
    "incomplete",
    "incomplete_expired",
    "unpaid",
    "paused",
}


def _resolve_tenant_id(db: Session, tenant_hint: str) -> int:
    if not tenant_hint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant_value = tenant_hint.strip()
    tenant = (
        get_tenant_by_id(db, int(tenant_value))
        if tenant_value.isdigit()
        else get_tenant_by_slug(db, tenant_value)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant.id


def _require_stripe_key() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe is not configured",
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _require_webhook_secret() -> None:
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe webhook secret is not configured",
        )


def _resolve_return_url(request: Request, suffix: str) -> str:
    base = settings.APP_BASE_URL
    if not base:
        base = request.headers.get("origin")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/billing?checkout={suffix}"


def _unix_to_datetime(value: int | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)


def _extract_price_id(subscription_obj: dict) -> str | None:
    items = subscription_obj.get("items", {}) if isinstance(subscription_obj, dict) else {}
    data = items.get("data", []) if isinstance(items, dict) else []
    if not data:
        return None
    price = data[0].get("price") if isinstance(data[0], dict) else None
    return price.get("id") if isinstance(price, dict) else None


def _resolve_tenant_id_from_payload(
    db: Session,
    *,
    tenant_hint: str | None,
    stripe_subscription_id: str | None,
    stripe_customer_id: str | None,
) -> int | None:
    if tenant_hint and tenant_hint.isdigit():
        return int(tenant_hint)
    if tenant_hint:
        try:
            return _resolve_tenant_id(db, tenant_hint)
        except HTTPException:
            pass
    existing = get_subscription_by_stripe_ids(
        db,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
    )
    return existing.tenant_id if existing else None


@router.post("/checkout", response_model=CheckoutSessionResponse)
def create_checkout_session(
    payload: CheckoutSessionCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx=Depends(
        require_role_in_tenant(
            [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.BILLING_ADMIN],
            user_resolver=get_current_user,
        )
    ),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    plan_key = normalize_plan_key(payload.plan_key)
    if not plan_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan key is required")
    if plan_key == "free":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Free plan does not require checkout")
    price_id = get_price_id(plan_key)
    if not price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is not available for checkout")
    plan_name = get_plan_name(plan_key)
    if not plan_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported plan key")
    plan = get_plan_by_name(db, plan_name)
    if not plan:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan not configured")

    _require_stripe_key()
    existing = get_latest_subscription_for_tenant(db, tenant_id)
    customer_id = existing.stripe_customer_id if existing else None

    success_url = _resolve_return_url(request, "success")
    cancel_url = _resolve_return_url(request, "cancel")

    session_params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(tenant_id),
        "metadata": {"tenant_id": str(tenant_id), "plan_key": plan_key},
        "subscription_data": {"metadata": {"tenant_id": str(tenant_id), "plan_key": plan_key}},
    }
    if customer_id:
        session_params["customer"] = customer_id

    session = stripe.checkout.Session.create(**session_params)
    create_audit_log(
        db,
        tenant_id=tenant_id,
        username=None,
        event=f"billing.checkout.started:{plan_key}",
        request=request,
    )
    return CheckoutSessionResponse(checkout_url=session.url)


@router.post("/portal", response_model=PortalSessionResponse)
def create_portal_session(
    request: Request,
    db: Session = Depends(get_db),
    ctx=Depends(
        require_role_in_tenant(
            [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.BILLING_ADMIN],
            user_resolver=get_current_user,
        )
    ),
):
    tenant_id = _resolve_tenant_id(db, ctx.tenant_id)
    subscription = get_latest_subscription_for_tenant(db, tenant_id)
    if not subscription or not subscription.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe customer not found")
    _require_stripe_key()
    return_url = settings.APP_BASE_URL or request.headers.get("origin") or str(request.base_url).rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=return_url,
    )
    return PortalSessionResponse(portal_url=session.url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    _require_webhook_secret()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature") from exc

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        tenant_hint = data_object.get("metadata", {}).get("tenant_id")
        plan_key = data_object.get("metadata", {}).get("plan_key")
        stripe_customer_id = data_object.get("customer")
        stripe_subscription_id = data_object.get("subscription")
        tenant_id = _resolve_tenant_id_from_payload(
            db,
            tenant_hint=tenant_hint,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
        )
        if tenant_id and plan_key:
            plan_name = get_plan_name(plan_key)
            plan = get_plan_by_name(db, plan_name) if plan_name else None
            if plan:
                upsert_stripe_subscription(
                    db,
                    tenant_id=tenant_id,
                    plan=plan,
                    plan_key=plan_key,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    status="active",
                )
                create_audit_log(
                    db,
                    tenant_id=tenant_id,
                    username=None,
                    event=f"billing.checkout.completed:{plan_key}",
                    request=request,
                )
                try:
                    process_referral_conversion(db, new_tenant_id=tenant_id)
                except Exception:
                    pass
                try:
                    process_affiliate_conversion(
                        db,
                        tenant_id=tenant_id,
                        stripe_subscription_id=stripe_subscription_id,
                    )
                except Exception:
                    pass

    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        stripe_customer_id = data_object.get("customer")
        stripe_subscription_id = data_object.get("id")
        tenant_hint = data_object.get("metadata", {}).get("tenant_id")
        price_id = _extract_price_id(data_object)
        plan_key = plan_key_from_price_id(price_id) or data_object.get("metadata", {}).get("plan_key")
        tenant_id = _resolve_tenant_id_from_payload(
            db,
            tenant_hint=tenant_hint,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
        )
        if tenant_id and plan_key:
            plan_name = get_plan_name(plan_key)
            plan = get_plan_by_name(db, plan_name) if plan_name else None
            if plan:
                status_value = data_object.get("status", "active")
                if status_value not in ALLOWED_STATUSES:
                    status_value = "canceled"
                upsert_stripe_subscription(
                    db,
                    tenant_id=tenant_id,
                    plan=plan,
                    plan_key=plan_key,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    status=status_value,
                    current_period_start=_unix_to_datetime(data_object.get("current_period_start")),
                    current_period_end=_unix_to_datetime(data_object.get("current_period_end")),
                    cancel_at_period_end=bool(data_object.get("cancel_at_period_end")),
                )
                create_audit_log(
                    db,
                    tenant_id=tenant_id,
                    username=None,
                    event=f"billing.subscription.{event_type}:{plan_key}",
                    request=request,
                )
                if status_value in {"active", "trialing"}:
                    try:
                        process_referral_conversion(db, new_tenant_id=tenant_id)
                    except Exception:
                        pass
                    try:
                        process_affiliate_conversion(
                            db,
                            tenant_id=tenant_id,
                            stripe_subscription_id=stripe_subscription_id,
                        )
                    except Exception:
                        pass
                else:
                    try:
                        void_affiliate_commission(
                            db,
                            tenant_id=tenant_id,
                            stripe_subscription_id=stripe_subscription_id,
                            reason=f\"subscription_{status_value}\",
                        )
                    except Exception:
                        pass

    elif event_type == "invoice.paid":
        stripe_subscription_id = data_object.get("subscription")
        subscription = get_subscription_by_stripe_ids(
            db,
            stripe_subscription_id=stripe_subscription_id,
        )
        if subscription:
            subscription.status = "active"
            db.commit()
            create_audit_log(
                db,
                tenant_id=subscription.tenant_id,
                username=None,
                event="billing.invoice.paid",
                request=request,
            )
            try:
                process_affiliate_conversion(
                    db,
                    tenant_id=subscription.tenant_id,
                    stripe_subscription_id=stripe_subscription_id,
                )
            except Exception:
                pass
    elif event_type == "invoice.payment_failed":
        stripe_subscription_id = data_object.get("subscription")
        subscription = get_subscription_by_stripe_ids(
            db,
            stripe_subscription_id=stripe_subscription_id,
        )
        if subscription:
            subscription.status = "past_due"
            db.commit()
            create_audit_log(
                db,
                tenant_id=subscription.tenant_id,
                username=None,
                event="billing.invoice.payment_failed",
                request=request,
            )
            try:
                void_affiliate_commission(
                    db,
                    tenant_id=subscription.tenant_id,
                    stripe_subscription_id=stripe_subscription_id,
                    reason="invoice_payment_failed",
                )
            except Exception:
                pass

    return {"received": True}
