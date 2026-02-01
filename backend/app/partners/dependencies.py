from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models.affiliates import AffiliatePartner
from app.models.partners import PartnerUser


@dataclass
class PartnerContext:
    user: object
    partner: AffiliatePartner
    partner_user: PartnerUser


def require_partner_context():
    def dependency(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> PartnerContext:
        partner_user = (
            db.query(PartnerUser)
            .filter(PartnerUser.user_id == current_user.id)
            .first()
        )
        if not partner_user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Partner access required")
        partner = (
            db.query(AffiliatePartner)
            .filter(AffiliatePartner.id == partner_user.partner_id)
            .first()
        )
        if not partner or partner.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Partner access inactive")
        return PartnerContext(user=current_user, partner=partner, partner_user=partner_user)

    return dependency


def require_partner_admin():
    def dependency(ctx: PartnerContext = Depends(require_partner_context())) -> PartnerContext:
        if ctx.partner_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Partner admin required")
        return ctx

    return dependency
