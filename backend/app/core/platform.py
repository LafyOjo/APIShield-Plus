from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenants import Tenant

logger = logging.getLogger(__name__)


def resolve_platform_audit_tenant_id(db: Session) -> int | None:
    preferred = settings.PLATFORM_AUDIT_TENANT_ID
    if preferred is not None:
        tenant = db.query(Tenant).filter(Tenant.id == preferred).first()
        if tenant:
            return tenant.id
        logger.warning("platform audit tenant not found", extra={"tenant_id": preferred})

    fallback = db.query(Tenant).order_by(Tenant.id.asc()).first()
    if fallback:
        return fallback.id
    logger.warning("no tenants available for platform audit logging")
    return None
