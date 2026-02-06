from sqlalchemy.orm import Session

from app.models.resellers import ResellerAccount, ManagedTenant


ALLOWED_BILLING_MODES = {"customer_pays_stripe", "reseller_pays_invoice"}


def create_reseller_account(
    db: Session,
    *,
    partner_id: int,
    billing_mode: str = "customer_pays_stripe",
    allowed_plans: list[str] | None = None,
    is_enabled: bool = True,
) -> ResellerAccount:
    if billing_mode not in ALLOWED_BILLING_MODES:
        raise ValueError("Invalid billing mode")
    account = ResellerAccount(
        partner_id=partner_id,
        billing_mode=billing_mode,
        allowed_plans=allowed_plans,
        is_enabled=is_enabled,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get_reseller_account(db: Session, *, partner_id: int) -> ResellerAccount | None:
    return (
        db.query(ResellerAccount)
        .filter(ResellerAccount.partner_id == partner_id)
        .first()
    )


def get_managed_tenant(db: Session, *, tenant_id: int) -> ManagedTenant | None:
    return (
        db.query(ManagedTenant)
        .filter(ManagedTenant.tenant_id == tenant_id)
        .first()
    )


def list_managed_tenants(db: Session, *, partner_id: int) -> list[ManagedTenant]:
    return (
        db.query(ManagedTenant)
        .filter(ManagedTenant.reseller_partner_id == partner_id)
        .order_by(ManagedTenant.created_at.desc())
        .all()
    )


def create_managed_tenant(
    db: Session,
    *,
    partner_id: int,
    tenant_id: int,
    status: str = "active",
) -> ManagedTenant:
    existing = get_managed_tenant(db, tenant_id=tenant_id)
    if existing:
        return existing
    record = ManagedTenant(
        reseller_partner_id=partner_id,
        tenant_id=tenant_id,
        status=status,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
