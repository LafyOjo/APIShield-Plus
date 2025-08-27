# This router exposes two small endpoints around “alerts”: one that returns
# the raw list, and one that returns a pre-aggregated time series for charts.
# I’m keeping the router skinny on purpose — all database details live in CRUD
# or the ORM models, while this layer just wires dependencies and shapes output.
# That separation makes it easy to test and swap implementations later.

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

# Pull in the database session factory and the CRUD accessor. I want each
# request to get a fresh Session via Depends(get_db), which keeps connection
# handling consistent and safe. The CRUD function (get_all_alerts) is the
# single source of truth for how we fetch the raw alert rows from storage.
from app.core.db import get_db
from app.crud.alerts import get_all_alerts

# These Pydantic schemas define the shape of what we send back to clients.
# Using explicit response models gives us a stable contract and automatic
# OpenAPI docs, and helps ensure we don’t accidentally leak internal fields.
# The Alert ORM model is used only for building SQL queries in the stats view.
from app.schemas.alerts import AlertRead, AlertStat
from app.api.dependencies import get_current_user
from app.models.alerts import Alert

# Standard FastAPI router setup: everything here gets the /api/alerts prefix,
# and the "alerts" tag groups it nicely in the interactive docs. Keeping a
# dedicated router per domain (alerts, users, logs, etc.) keeps the codebase
# tidy and makes it trivial to include or exclude features when composing the app.
router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
)

# This endpoint returns the raw list of alerts as-is from the CRUD layer.
# It’s useful for tables or developer tools that want the full record
# without any aggregation. We purposely keep auth/filters out here to keep
# the example simple; real apps might page, filter, or scope by user/role.
@router.get("/", response_model=list[AlertRead])
def read_alerts(db: Session = Depends(get_db)):
    return get_all_alerts(db)

# This endpoint powers the chart view by grouping alerts into minute buckets
# and counting two categories: “blocked” and “invalid”. The idea is to show
# at-a-glance whether our defenses are blocking traffic or simply detecting
# bad attempts. We also require a current user (even if unused) to enforce auth.
@router.get("/stats", response_model=list[AlertStat])
def read_alert_stats(
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Aggregate alert counts per minute."""

    # Build a compact aggregation query:
    # - time bucket: we floor timestamps to the minute using strftime.
    # - blocked: count rows whose detail starts with "Blocked:" (treated as 1).
    # - invalid: count everything else (treated as 1 when NOT “Blocked:”).
    # Using SQL’s CASE + SUM keeps the whole computation in the database,
    # which is faster and avoids hauling raw rows into Python just to count.
    rows = (
        db.query(
            func.strftime("%Y-%m-%d %H:%M:00", Alert.timestamp).label("time"),
            func.sum(
                case((Alert.detail.like("Blocked:%"), 1), else_=0)
            ).label("blocked"),
            func.sum(
                case((Alert.detail.like("Blocked:%"), 0), else_=1)
            ).label("invalid"),
        )
        .group_by("time")
        .order_by("time")
        .all()
    )

    # Shape the rows into a clean, typed payload that matches AlertStat.
    # I cast values to int because some SQL engines return Decimal/long types,
    # and I want clients to see simple JSON numbers. Returning a plain list of
    # dicts also keeps the response lightweight and easy to consume in charts.
    return [
        {"time": row.time, "invalid": int(row.invalid), "blocked": int(row.blocked)}
        for row in rows
    ]
