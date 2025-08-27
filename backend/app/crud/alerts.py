# This file contains a helper to fetch alerts from the database.
# Alerts usually represent suspicious or blocked activity (like
# failed logins or stuffing attempts). Admins can review them
# later in the dashboard.

from sqlalchemy.orm import Session
from app.models.alerts import Alert


# Return every alert in the database. No filters here — the
# caller (like an API endpoint) can apply any sorting, paging,
# or trimming logic. Useful for admin overviews or exports.
def get_all_alerts(db: Session) -> list[Alert]:
    return db.query(Alert).all()
