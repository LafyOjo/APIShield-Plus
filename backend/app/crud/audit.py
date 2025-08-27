# Audit logs record key system events, like authentication or
# sensitive changes. Unlike access logs, these are higher-level
# and meant for compliance or security monitoring.

from sqlalchemy.orm import Session
from app.models.audit_logs import AuditLog


# Insert a new audit log entry into the database. You pass in
# the user (or None if anonymous) and the event string to store.
# Once committed, the fresh log object is returned to the caller.
def create_audit_log(db: Session, username: str | None, event: str) -> AuditLog:
    log = AuditLog(username=username, event=event)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
