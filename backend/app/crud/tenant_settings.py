from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant_settings import TenantSettings


def _default_alert_prefs() -> dict:
    return {
        "email_alerts": True,
        "severity_threshold": "medium",
        "fail_limit": settings.FAIL_LIMIT,
    }


def create_default_settings(
    db: Session,
    tenant_id: int,
    *,
    raw_ip_retention_days: int | None = None,
) -> TenantSettings:
    default_raw_ip_days = 7 if raw_ip_retention_days is None else raw_ip_retention_days
    settings_row = TenantSettings(
        tenant_id=tenant_id,
        timezone="UTC",
        retention_days=30,
        event_retention_days=30,
        ip_raw_retention_days=default_raw_ip_days,
        alert_prefs=_default_alert_prefs(),
    )
    db.add(settings_row)
    db.flush()
    return settings_row


def get_settings(db: Session, tenant_id: int) -> TenantSettings:
    settings_row = (
        db.query(TenantSettings)
        .filter(TenantSettings.tenant_id == tenant_id)
        .first()
    )
    if settings_row:
        return settings_row
    raw_ip_retention_days = None
    try:
        from app.core.entitlements import get_tenant_plan

        plan = get_tenant_plan(db, tenant_id)
        if plan:
            limit_value = (plan.limits_json or {}).get("raw_ip_retention_days")
            if isinstance(limit_value, int) and limit_value > 0:
                raw_ip_retention_days = limit_value
    except Exception:
        raw_ip_retention_days = None
    settings_row = create_default_settings(
        db,
        tenant_id,
        raw_ip_retention_days=raw_ip_retention_days,
    )
    db.commit()
    db.refresh(settings_row)
    return settings_row


def update_settings(db: Session, tenant_id: int, changes: dict) -> TenantSettings:
    settings_row = get_settings(db, tenant_id)
    if "timezone" in changes and changes["timezone"] is not None:
        settings_row.timezone = changes["timezone"]
    if "retention_days" in changes and changes["retention_days"] is not None:
        settings_row.retention_days = changes["retention_days"]
        settings_row.event_retention_days = changes["retention_days"]
    if "event_retention_days" in changes and changes["event_retention_days"] is not None:
        settings_row.event_retention_days = changes["event_retention_days"]
        settings_row.retention_days = changes["event_retention_days"]
    if "ip_raw_retention_days" in changes and changes["ip_raw_retention_days"] is not None:
        settings_row.ip_raw_retention_days = changes["ip_raw_retention_days"]
    if "alert_prefs" in changes and changes["alert_prefs"] is not None:
        current = settings_row.alert_prefs or {}
        incoming = changes["alert_prefs"]
        settings_row.alert_prefs = {**current, **incoming}
    db.commit()
    db.refresh(settings_row)
    return settings_row
