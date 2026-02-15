from datetime import datetime

from pydantic import BaseModel


class CheckoutSessionCreate(BaseModel):
    plan_key: str


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionResponse(BaseModel):
    portal_url: str


class BillingPlanOption(BaseModel):
    plan_key: str
    plan_name: str
    checkout_available: bool
    contact_sales: bool = False


class BillingStatusResponse(BaseModel):
    tenant_id: int
    plan_key: str | None = None
    plan_name: str | None = None
    subscription_status: str | None = None
    provider: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    can_manage_billing: bool = False
    stripe_configured: bool = False
    webhook_configured: bool = False
    available_plans: list[BillingPlanOption] = []
