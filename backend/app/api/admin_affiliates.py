from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core.db import get_db
from app.core.affiliates import build_affiliate_link, generate_affiliate_code, build_partner_summary
from app.crud.affiliates import (
    create_partner,
    get_partner,
    list_partners,
    list_attributions_for_partner,
    list_commissions_for_partner,
    update_partner,
)
from app.models.affiliates import AffiliateCommissionLedger
from app.schemas.affiliates import (
    AffiliateAttributionRead,
    AffiliateCommissionRead,
    AffiliateLedgerUpdate,
    AffiliatePartnerCreate,
    AffiliatePartnerRead,
    AffiliatePartnerUpdate,
    AffiliateSummary,
)


router = APIRouter(prefix="/admin/affiliates", tags=["admin"])

ALLOWED_STATUSES = {"active", "paused"}
ALLOWED_COMMISSION_TYPES = {"percent", "flat"}
ALLOWED_LEDGER_STATUSES = {"pending", "earned", "paid", "void"}


def _partner_read(partner) -> AffiliatePartnerRead:
    return AffiliatePartnerRead(
        id=partner.id,
        name=partner.name,
        status=partner.status,
        code=partner.code,
        commission_type=partner.commission_type,
        commission_value=float(partner.commission_value or 0),
        payout_method=partner.payout_method,
        created_at=partner.created_at,
        updated_at=partner.updated_at,
    )


@router.get("/partners", response_model=list[AffiliatePartnerRead])
def list_affiliate_partners(
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partners = list_partners(db)
    return [_partner_read(partner) for partner in partners]


@router.post("/partners", response_model=AffiliatePartnerRead, status_code=status.HTTP_201_CREATED)
def create_affiliate_partner(
    payload: AffiliatePartnerCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    if payload.status and payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if payload.commission_type not in ALLOWED_COMMISSION_TYPES:
        raise HTTPException(status_code=422, detail="Invalid commission type")
    code = (payload.code or generate_affiliate_code()).strip().lower()
    partner = create_partner(
        db,
        name=payload.name,
        code=code,
        status=payload.status or "active",
        commission_type=payload.commission_type,
        commission_value=payload.commission_value,
    )
    return _partner_read(partner)


@router.patch("/partners/{partner_id}", response_model=AffiliatePartnerRead)
def update_affiliate_partner(
    partner_id: int,
    payload: AffiliatePartnerUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partner = get_partner(db, partner_id=partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    updates = payload.dict(exclude_unset=True)
    if "status" in updates and updates["status"] not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if "commission_type" in updates and updates["commission_type"] not in ALLOWED_COMMISSION_TYPES:
        raise HTTPException(status_code=422, detail="Invalid commission type")
    partner = update_partner(db, partner=partner, updates=updates)
    return _partner_read(partner)


@router.get("/partners/{partner_id}/summary", response_model=AffiliateSummary)
def affiliate_partner_summary(
    partner_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partner = get_partner(db, partner_id=partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    summary = build_partner_summary(db, partner_id=partner_id)
    return AffiliateSummary(partner_id=partner_id, **summary)


@router.get("/partners/{partner_id}/attributions", response_model=list[AffiliateAttributionRead])
def list_partner_attributions(
    partner_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partner = get_partner(db, partner_id=partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    rows = list_attributions_for_partner(db, partner_id=partner_id)
    return [
        AffiliateAttributionRead(
            id=row.id,
            partner_id=row.partner_id,
            tenant_id=row.tenant_id,
            first_touch_at=row.first_touch_at,
            last_touch_at=row.last_touch_at,
            source_meta=row.source_meta_json if isinstance(row.source_meta_json, dict) else None,
        )
        for row in rows
    ]


@router.get("/partners/{partner_id}/ledger", response_model=list[AffiliateCommissionRead])
def list_partner_commissions(
    partner_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partner = get_partner(db, partner_id=partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    rows = list_commissions_for_partner(db, partner_id=partner_id)
    return [
        AffiliateCommissionRead(
            id=row.id,
            partner_id=row.partner_id,
            tenant_id=row.tenant_id,
            stripe_subscription_id=row.stripe_subscription_id,
            amount=float(row.amount or 0),
            currency=row.currency,
            status=row.status,
            earned_at=row.earned_at,
            paid_at=row.paid_at,
            void_reason=row.void_reason,
        )
        for row in rows
    ]


@router.post("/ledger/{ledger_id}", response_model=AffiliateCommissionRead)
def update_commission_ledger(
    ledger_id: int,
    payload: AffiliateLedgerUpdate,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    ledger = db.query(AffiliateCommissionLedger).filter(AffiliateCommissionLedger.id == ledger_id).first()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    if payload.status not in ALLOWED_LEDGER_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if payload.status == "void" and not payload.void_reason:
        raise HTTPException(status_code=422, detail="Void reason required")
    ledger.status = payload.status
    if payload.status == "paid":
        ledger.paid_at = payload.paid_at or datetime.utcnow()
    if payload.status == "void":
        ledger.void_reason = payload.void_reason
        ledger.paid_at = None
    db.commit()
    db.refresh(ledger)
    return AffiliateCommissionRead(
        id=ledger.id,
        partner_id=ledger.partner_id,
        tenant_id=ledger.tenant_id,
        stripe_subscription_id=ledger.stripe_subscription_id,
        amount=float(ledger.amount or 0),
        currency=ledger.currency,
        status=ledger.status,
        earned_at=ledger.earned_at,
        paid_at=ledger.paid_at,
        void_reason=ledger.void_reason,
    )


@router.get("/partners/{partner_id}/link")
def get_partner_link(
    partner_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_platform_admin()),
):
    partner = get_partner(db, partner_id=partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return {"code": partner.code, "link": build_affiliate_link(partner.code)}
