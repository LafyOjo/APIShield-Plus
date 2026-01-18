# Audit logs record key system events, like authentication or
# sensitive changes. Unlike access logs, these are higher-level
# and meant for compliance or security monitoring.

from sqlalchemy.orm import Session
from app.models.audit_logs import AuditLog


# Insert a new audit log entry into the database. You pass in
# the user (or None if anonymous) and the event string to store.
# Once committed, the fresh log object is returned to the caller.
def create_audit_log(
    db: Session,
    tenant_id: int,
    username: str | None,
    event: str,
) -> AuditLog:
    if tenant_id is None:
        raise ValueError("tenant_id is required to create an audit log entry")
    log = AuditLog(tenant_id=tenant_id, username=username, event=event)
    db.add(log)
    db.commit()
    db.refresh(log)
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
