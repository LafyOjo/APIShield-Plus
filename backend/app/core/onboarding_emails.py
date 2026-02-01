from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.email_queue import create_email_queue, get_latest_email, recently_queued
from app.models.behaviour_events import BehaviourEvent
from app.models.enums import MembershipStatusEnum, RoleEnum
from app.models.memberships import Membership
from app.models.tenants import Tenant
from app.models.users import User
from app.models.user_profiles import UserProfile


TEMPLATE_WELCOME = "welcome"
TEMPLATE_NO_EVENTS = "no_events_nudge"
TEMPLATE_FIRST_EVENT = "first_event_map_wow"
TEMPLATE_FIRST_INCIDENT = "first_incident"
TEMPLATE_UPGRADE_NUDGE = "upgrade_nudge"

TEMPLATE_FILES = {
    TEMPLATE_WELCOME,
    TEMPLATE_NO_EVENTS,
    TEMPLATE_FIRST_EVENT,
    TEMPLATE_FIRST_INCIDENT,
    TEMPLATE_UPGRADE_NUDGE,
}

FEATURE_LABELS = {
    "geo_map": "Geo Activity Map",
    "revenue_leaks": "Revenue Leak Heatmaps",
    "remediation_workspace": "Remediation Workspace",
    "verification": "Verification Checks",
    "data_exports": "Data Exports",
    "incident_exports": "Incident Reports",
}


@dataclass(frozen=True)
class EmailTemplate:
    key: str
    subject: str
    body: str
    preheader: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    cooldown_hours: int | None = None


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _template_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "emails"


def _parse_front_matter(contents: str) -> tuple[dict[str, str], str]:
    if not contents.startswith("---"):
        return {}, contents
    parts = contents.split("---", 2)
    if len(parts) < 3:
        return {}, contents
    meta_block = parts[1].strip().splitlines()
    body = parts[2].lstrip("\n")
    meta: dict[str, str] = {}
    for line in meta_block:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip()
    return meta, body


def load_email_template(key: str) -> EmailTemplate:
    normalized = key.strip().lower()
    if normalized not in TEMPLATE_FILES:
        raise ValueError(f"Unknown email template: {key}")
    path = _template_dir() / f"{normalized}.md"
    contents = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(contents)
    cooldown = meta.get("cooldown_hours")
    cooldown_hours = int(cooldown) if cooldown and cooldown.isdigit() else None
    return EmailTemplate(
        key=normalized,
        subject=meta.get("subject", normalized),
        body=body.strip(),
        preheader=meta.get("preheader"),
        cta_label=meta.get("cta_label"),
        cta_url=meta.get("cta_url"),
        cooldown_hours=cooldown_hours,
    )


def _app_base_url() -> str:
    return (
        settings.APP_BASE_URL
        or settings.FRONTEND_BASE_URL
        or "http://localhost:3000"
    )


def _display_name(user: User | None) -> str:
    if not user:
        return "there"
    profile = getattr(user, "profile", None)
    if profile and profile.display_name:
        return profile.display_name
    username = user.username or "there"
    if "@" in username:
        return username.split("@", 1)[0]
    return username


def _is_opted_out(db: Session, user: User | None) -> bool:
    if not user:
        return False
    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == user.id)
        .first()
    )
    return bool(profile.email_opt_out) if profile else False


def _primary_contact(db: Session, tenant_id: int) -> User | None:
    row = (
        db.query(User)
        .join(Membership, Membership.user_id == User.id)
        .filter(
            Membership.tenant_id == tenant_id,
            Membership.status == MembershipStatusEnum.ACTIVE,
            Membership.role == RoleEnum.OWNER,
        )
        .order_by(Membership.created_at.asc())
        .first()
    )
    return row


def _render_template(template: EmailTemplate, context: dict[str, Any]) -> tuple[str, str, str | None]:
    safe_context = _SafeDict(context)
    subject = template.subject.format_map(safe_context)
    body = template.body.format_map(safe_context)
    cta_url = template.cta_url.format_map(safe_context) if template.cta_url else None
    return subject, body, cta_url


def queue_onboarding_email(
    db: Session,
    *,
    tenant: Tenant,
    user: User,
    template_key: str,
    trigger_event: str,
    context: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    if not tenant or not user:
        return False
    if not settings.EMAILS_ENABLED:
        return False
    if _is_opted_out(db, user):
        return False
    try:
        template = load_email_template(template_key)
    except Exception:
        return False
    final_dedupe = dedupe_key or template.key
    existing = get_latest_email(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        dedupe_key=final_dedupe,
    )
    if existing:
        return False
    if recently_queued(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        dedupe_key=final_dedupe,
        cooldown_hours=template.cooldown_hours,
    ):
        return False
    base_context = {
        "user_name": _display_name(user),
        "tenant_name": tenant.name,
        "app_base_url": _app_base_url(),
    }
    if context:
        base_context.update(context)
    subject, body, cta_url = _render_template(template, base_context)
    metadata = {
        "preheader": template.preheader,
        "cta_label": template.cta_label,
        "cta_url": cta_url,
        "context": {
            k: base_context.get(k)
            for k in ("feature_name", "incident_id", "upgrade_source")
            if k in base_context
        },
    }
    return bool(
        create_email_queue(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            to_email=user.username,
            template_key=template.key,
            dedupe_key=final_dedupe,
            trigger_event=trigger_event,
            subject=subject,
            body=body,
            metadata=metadata,
        )
    )


def queue_welcome_email(db: Session, *, tenant: Tenant, user: User) -> bool:
    return queue_onboarding_email(
        db,
        tenant=tenant,
        user=user,
        template_key=TEMPLATE_WELCOME,
        trigger_event="signup",
        dedupe_key="welcome",
    )


def queue_no_events_nudge(db: Session, *, tenant: Tenant, user: User) -> bool:
    return queue_onboarding_email(
        db,
        tenant=tenant,
        user=user,
        template_key=TEMPLATE_NO_EVENTS,
        trigger_event="no_events_after_time",
        dedupe_key="no_events_after_time",
    )


def queue_first_event_email(db: Session, *, tenant_id: int) -> bool:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant or tenant.is_demo_mode or tenant.deleted_at is not None:
        return False
    user = _primary_contact(db, tenant_id)
    if not user:
        return False
    existing = get_latest_email(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        dedupe_key="first_event_received",
    )
    if existing:
        return False
    has_event = (
        db.query(BehaviourEvent.id)
        .filter(
            BehaviourEvent.tenant_id == tenant_id,
            BehaviourEvent.is_demo.is_(False),
        )
        .limit(2)
        .all()
    )
    if len(has_event) != 1:
        return False
    return queue_onboarding_email(
        db,
        tenant=tenant,
        user=user,
        template_key=TEMPLATE_FIRST_EVENT,
        trigger_event="first_event_received",
        dedupe_key="first_event_received",
    )


def queue_first_incident_email(
    db: Session,
    *,
    tenant_id: int,
    incident_id: int,
) -> bool:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant or tenant.is_demo_mode or tenant.deleted_at is not None:
        return False
    user = _primary_contact(db, tenant_id)
    if not user:
        return False
    return queue_onboarding_email(
        db,
        tenant=tenant,
        user=user,
        template_key=TEMPLATE_FIRST_INCIDENT,
        trigger_event="first_incident_created",
        dedupe_key="first_incident_created",
        context={"incident_id": incident_id},
    )


def queue_upgrade_nudge(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    feature_key: str,
    source: str | None = None,
) -> bool:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    if not tenant or not user or tenant.deleted_at is not None:
        return False
    feature_name = FEATURE_LABELS.get(feature_key, feature_key.replace("_", " ").title())
    dedupe = f"upgrade:{feature_key}"
    return queue_onboarding_email(
        db,
        tenant=tenant,
        user=user,
        template_key=TEMPLATE_UPGRADE_NUDGE,
        trigger_event="feature_locked_clicked",
        dedupe_key=dedupe,
        context={
            "feature_name": feature_name,
            "upgrade_source": source or "",
        },
    )


def run_no_events_nudge_job(
    db: Session,
    *,
    now: datetime | None = None,
    threshold_hours: int = 2,
) -> int:
    now = now or datetime.utcnow()
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=threshold_hours)
    tenants = (
        db.query(Tenant)
        .filter(
            Tenant.created_at <= cutoff,
            Tenant.deleted_at.is_(None),
            Tenant.is_demo_mode.is_(False),
        )
        .all()
    )
    queued = 0
    for tenant in tenants:
        has_event = (
            db.query(BehaviourEvent.id)
            .filter(
                BehaviourEvent.tenant_id == tenant.id,
                BehaviourEvent.is_demo.is_(False),
            )
            .first()
        )
        if has_event:
            continue
        user = _primary_contact(db, tenant.id)
        if not user:
            continue
        if queue_no_events_nudge(db, tenant=tenant, user=user):
            queued += 1
    return queued
