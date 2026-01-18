# Audit logs record key system events, like authentication or
# sensitive changes. Unlike access logs, these are higher-level
# and meant for compliance or security monitoring.

import logging
from sqlalchemy.orm import Session

from app.core.privacy import hash_ip
from app.core.request_meta import resolve_request_meta
from app.models.audit_logs import AuditLog

logger = logging.getLogger(__name__)


# Insert a new audit log entry into the database. You pass in
# the user (or None if anonymous) and the event string to store.
# Once committed, the fresh log object is returned to the caller.
def create_audit_log(
    db: Session,
    tenant_id: int,
    username: str | None,
    event: str,
    *,
    request=None,
    request_meta: dict[str, str | None] | None = None,
    client_ip: str | None = None,
    ip_hash: str | None = None,
    user_agent: str | None = None,
    request_path: str | None = None,
    referrer: str | None = None,
    country_code: str | None = None,
    region: str | None = None,
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    asn: str | None = None,
    is_datacenter: bool | None = None,
) -> AuditLog:
    if tenant_id is None:
        raise ValueError("tenant_id is required to create an audit log entry")
    meta = resolve_request_meta(request=request, request_meta=request_meta)
    resolved_client_ip = client_ip or (meta.get("client_ip") if meta else None)
    resolved_user_agent = user_agent or (meta.get("user_agent") if meta else None)
    resolved_request_path = request_path or (meta.get("path") if meta else None)
    resolved_referrer = referrer or (meta.get("referer") if meta else None)
    if resolved_client_ip and ip_hash is None:
        try:
            ip_hash = hash_ip(tenant_id, resolved_client_ip)
        except ValueError:
            ip_hash = None
    log = AuditLog(tenant_id=tenant_id, username=username, event=event)
    log.client_ip = resolved_client_ip
    log.ip_hash = ip_hash
    log.user_agent = resolved_user_agent
    log.request_path = resolved_request_path
    log.referrer = resolved_referrer
    log.country_code = country_code
    log.region = region
    log.city = city
    log.latitude = latitude
    log.longitude = longitude
    log.asn = asn
    log.is_datacenter = is_datacenter
    db.add(log)
    db.commit()
    db.refresh(log)
    if meta:
        logger.debug(
            "audit.logged",
            extra={
                "tenant_id": tenant_id,
                "username": username,
                "event": event,
                "request_id": meta.get("request_id"),
                "client_ip": meta.get("client_ip"),
            },
        )
    return log


def get_audit_logs(
    db: Session,
    tenant_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
