from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.activation_metrics import ActivationMetric
from app.models.audit_logs import AuditLog
from app.models.behaviour_events import BehaviourEvent
from app.models.growth_metrics import GrowthSnapshot
from app.models.incidents import Incident
from app.models.prescriptions import PrescriptionItem
from app.models.subscriptions import Subscription
from app.models.tenants import Tenant


def _normalize_ts(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day)
    return start, start + timedelta(days=1)


def _week_start(dt: datetime) -> date:
    anchor = dt.date()
    return anchor - timedelta(days=anchor.weekday())


def _parse_paywall_event(event: str) -> tuple[str, str, str | None] | None:
    if not event or not event.startswith("paywall."):
        return None
    parts = event.split(":")
    if len(parts) < 2:
        return None
    action = parts[0].split(".", 1)[-1]
    feature = parts[1]
    source = parts[2] if len(parts) > 2 else None
    return action, feature, source


def _resolve_paid_tenants(db: Session) -> set[int]:
    rows = (
        db.query(Subscription.tenant_id)
        .filter(
            Subscription.plan_key.isnot(None),
            Subscription.plan_key != "free",
            Subscription.status.in_(["active", "trialing"]),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _first_event_subquery(db: Session):
    query = db.query(
        BehaviourEvent.tenant_id,
        func.min(BehaviourEvent.ingested_at).label("first_event"),
    ).group_by(BehaviourEvent.tenant_id)
    if hasattr(BehaviourEvent, "is_demo"):
        query = query.filter(BehaviourEvent.is_demo.is_(False))
    return query.subquery()


def _first_incident_subquery(db: Session):
    query = db.query(
        Incident.tenant_id,
        func.min(Incident.created_at).label("first_incident"),
    ).group_by(Incident.tenant_id)
    if hasattr(Incident, "is_demo"):
        query = query.filter(Incident.is_demo.is_(False))
    return query.subquery()


def _first_prescription_subquery(db: Session):
    query = (
        db.query(
            PrescriptionItem.tenant_id,
            func.min(PrescriptionItem.applied_at).label("first_prescription"),
        )
        .filter(PrescriptionItem.applied_at.isnot(None))
        .group_by(PrescriptionItem.tenant_id)
    )
    return query.subquery()


def _upsert_growth_snapshot(
    db: Session,
    *,
    snapshot_date: date,
    payload: dict,
) -> GrowthSnapshot:
    snapshot = (
        db.query(GrowthSnapshot)
        .filter(GrowthSnapshot.snapshot_date == snapshot_date)
        .first()
    )
    if snapshot is None:
        snapshot = GrowthSnapshot(snapshot_date=snapshot_date)
        db.add(snapshot)
    for key, value in payload.items():
        setattr(snapshot, key, value)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def run_growth_metrics_job(db: Session, *, snapshot_date: date | None = None, lookback_days: int = 1) -> GrowthSnapshot | None:
    today = (snapshot_date or utcnow().date())
    snapshot = None
    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        start, end = _day_bounds(day)

        tenants_query = db.query(Tenant).filter(Tenant.is_demo_mode.is_(False))
        signups = (
            tenants_query
            .filter(Tenant.created_at >= start, Tenant.created_at < end)
            .count()
        )

        first_event_subq = _first_event_subquery(db)
        first_incident_subq = _first_incident_subquery(db)
        first_prescription_subq = _first_prescription_subquery(db)

        active_tenant_ids = [row[0] for row in db.query(Tenant.id).filter(Tenant.is_demo_mode.is_(False)).all()]

        activated = 0
        if active_tenant_ids:
            activated = (
                db.query(func.count(first_event_subq.c.tenant_id))
                .select_from(first_event_subq)
                .filter(
                    first_event_subq.c.tenant_id.in_(active_tenant_ids),
                    first_event_subq.c.first_event >= start,
                    first_event_subq.c.first_event < end,
                )
                .scalar()
                or 0
            )

        onboarding_completed = (
            db.query(func.count(ActivationMetric.tenant_id))
            .join(Tenant, Tenant.id == ActivationMetric.tenant_id)
            .filter(
                Tenant.is_demo_mode.is_(False),
                ActivationMetric.onboarding_completed_at.isnot(None),
                ActivationMetric.onboarding_completed_at >= start,
                ActivationMetric.onboarding_completed_at < end,
            )
            .scalar()
            or 0
        )

        first_incident = 0
        if active_tenant_ids:
            first_incident = (
                db.query(func.count(first_incident_subq.c.tenant_id))
                .select_from(first_incident_subq)
                .filter(
                    first_incident_subq.c.tenant_id.in_(active_tenant_ids),
                    first_incident_subq.c.first_incident >= start,
                    first_incident_subq.c.first_incident < end,
                )
                .scalar()
                or 0
            )

        first_prescription = 0
        if active_tenant_ids:
            first_prescription = (
                db.query(func.count(first_prescription_subq.c.tenant_id))
                .select_from(first_prescription_subq)
                .filter(
                    first_prescription_subq.c.tenant_id.in_(active_tenant_ids),
                    first_prescription_subq.c.first_prescription >= start,
                    first_prescription_subq.c.first_prescription < end,
                )
                .scalar()
                or 0
            )

        avg_time_to_first = (
            db.query(func.avg(ActivationMetric.time_to_first_event_seconds))
            .join(Tenant, Tenant.id == ActivationMetric.tenant_id)
            .filter(
                Tenant.is_demo_mode.is_(False),
                Tenant.created_at >= start,
                Tenant.created_at < end,
                ActivationMetric.time_to_first_event_seconds.isnot(None),
            )
            .scalar()
        )

        upgrade_query = (
            db.query(func.count(func.distinct(AuditLog.tenant_id)))
            .filter(
                AuditLog.timestamp >= start,
                AuditLog.timestamp < end,
                AuditLog.event.like("billing.checkout.completed:%"),
            )
        )
        if active_tenant_ids:
            upgrade_query = upgrade_query.filter(AuditLog.tenant_id.in_(active_tenant_ids))
        upgraded = upgrade_query.scalar() or 0

        churn_query = (
            db.query(func.count(func.distinct(AuditLog.tenant_id)))
            .filter(
                AuditLog.timestamp >= start,
                AuditLog.timestamp < end,
                AuditLog.event.like("billing.subscription.customer.subscription.deleted:%"),
            )
        )
        if active_tenant_ids:
            churn_query = churn_query.filter(AuditLog.tenant_id.in_(active_tenant_ids))
        churned = churn_query.scalar() or 0

        funnel = {
            "signups": signups,
            "activated": activated,
            "onboarding_completed": onboarding_completed,
            "first_incident": first_incident,
            "first_prescription": first_prescription,
            "upgraded": upgraded,
        }

        # Cohorts
        cohort_stats: dict[date, dict] = defaultdict(lambda: {"total": 0, "activated": 0, "upgraded": 0})
        paid_tenants = _resolve_paid_tenants(db)
        first_event_map = {}
        if active_tenant_ids:
            rows = db.query(first_event_subq.c.tenant_id).select_from(first_event_subq).all()
            first_event_map = {row[0]: True for row in rows}

        for tenant in tenants_query:
            week = _week_start(tenant.created_at or utcnow())
            bucket = cohort_stats[week]
            bucket["total"] += 1
            if tenant.id in first_event_map:
                bucket["activated"] += 1
            if tenant.id in paid_tenants:
                bucket["upgraded"] += 1

        cohorts = []
        for week_start, values in sorted(cohort_stats.items(), key=lambda item: item[0]):
            total = values["total"] or 0
            activated_count = values["activated"]
            upgraded_count = values["upgraded"]
            cohorts.append(
                {
                    "week_start": week_start.isoformat(),
                    "total": total,
                    "activated": activated_count,
                    "upgraded": upgraded_count,
                    "activation_rate": activated_count / total if total else 0.0,
                    "upgrade_rate": upgraded_count / total if total else 0.0,
                }
            )

        # Paywall conversion stats
        paywall_counts: dict[tuple[str, str | None], dict[str, int]] = defaultdict(
            lambda: {"shown": 0, "cta_clicked": 0, "checkout_started": 0, "upgrades": 0}
        )
        latest_checkout: dict[int, tuple[datetime, str, str | None]] = {}

        paywall_query = (
            db.query(AuditLog)
            .filter(
                AuditLog.timestamp >= start,
                AuditLog.timestamp < end,
                AuditLog.event.like("paywall.%"),
            )
            .order_by(AuditLog.timestamp.asc())
        )
        if active_tenant_ids:
            paywall_query = paywall_query.filter(AuditLog.tenant_id.in_(active_tenant_ids))
        paywall_logs = paywall_query.all()
        for log in paywall_logs:
            parsed = _parse_paywall_event(log.event)
            if not parsed:
                continue
            action, feature, source = parsed
            key = (feature, source)
            if action in paywall_counts[key]:
                paywall_counts[key][action] += 1
            if action == "checkout_started":
                latest_checkout[log.tenant_id] = (log.timestamp, feature, source)

        checkout_query = (
            db.query(AuditLog)
            .filter(
                AuditLog.timestamp >= start,
                AuditLog.timestamp < end,
                AuditLog.event.like("billing.checkout.completed:%"),
            )
            .order_by(AuditLog.timestamp.asc())
        )
        if active_tenant_ids:
            checkout_query = checkout_query.filter(AuditLog.tenant_id.in_(active_tenant_ids))
        checkout_logs = checkout_query.all()
        for log in checkout_logs:
            if log.tenant_id in latest_checkout:
                _, feature, source = latest_checkout[log.tenant_id]
                paywall_counts[(feature, source)]["upgrades"] += 1

        paywall_stats = [
            {
                "feature_key": feature,
                "source": source or "",
                **counts,
            }
            for (feature, source), counts in paywall_counts.items()
        ]

        payload = {
            "signups": signups,
            "activated": activated,
            "onboarding_completed": onboarding_completed,
            "first_incident": first_incident,
            "first_prescription": first_prescription,
            "upgraded": upgraded,
            "churned": churned,
            "avg_time_to_first_event_seconds": float(avg_time_to_first) if avg_time_to_first else None,
            "funnel_json": funnel,
            "cohort_json": cohorts,
            "paywall_json": paywall_stats,
        }

        snapshot = _upsert_growth_snapshot(db, snapshot_date=day, payload=payload)

    return snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute growth metrics snapshots.")
    parser.add_argument("--date", type=str, default=None, help="Snapshot date (YYYY-MM-DD).")
    parser.add_argument("--lookback-days", type=int, default=1, help="Days to recompute.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    snapshot_date = None
    if args.date:
        snapshot_date = date.fromisoformat(args.date)
    with SessionLocal() as db:
        run_growth_metrics_job(db, snapshot_date=snapshot_date, lookback_days=args.lookback_days)


if __name__ == "__main__":
    main()
