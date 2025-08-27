# This file defines functions to create and fetch access logs.
# Each log represents a request made by a user to a specific
# path. These helpers keep the DB interactions tidy and simple.

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.access_logs import AccessLog


# Insert a new access log into the database. We capture the
# username (if known) and the path they hit. This gets called
# by middleware after requests are processed.
def create_access_log(db: Session, username: str | None, path: str) -> AccessLog:
    log = AccessLog(username=username, path=path)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


# Fetch logs from the database. You can filter by username to
# see just their activity, and/or by a time window in hours.
# Results are sorted by most recent first for convenience.
def get_access_logs(
    db: Session, username: str | None = None, hours: int | None = None
) -> list[AccessLog]:
    query = db.query(AccessLog)
    if username is not None:
        query = query.filter(AccessLog.username == username)
    if hours is not None:
        since = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(AccessLog.timestamp >= since)
    return query.order_by(AccessLog.timestamp.desc()).all()
