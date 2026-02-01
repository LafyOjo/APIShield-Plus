from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.privacy import hash_ip
from app.core.time import utcnow
from app.models.behaviour_events import BehaviourEvent
from app.models.behaviour_sessions import BehaviourSession
from app.models.geo_event_aggs import GeoEventAgg
from app.models.incidents import Incident
from app.models.ip_enrichments import IPEnrichment
from app.models.revenue_impact import ImpactEstimate
from app.models.revenue_leaks import RevenueLeakEstimate
from app.models.remediation_playbooks import RemediationPlaybook
from app.models.protection_presets import ProtectionPreset
from app.models.security_events import SecurityEvent
from app.models.tenants import Tenant
from app.models.trust_scoring import TrustFactorAgg, TrustSnapshot
from app.models.website_stack_profiles import WebsiteStackProfile
from app.models.websites import Website
from app.models.website_environments import WebsiteEnvironment
from app.playbooks.generator import generate_playbook_for_incident
from app.presets.generator import get_or_generate_presets


DEMO_LOOKBACK_HOURS = 24
DEMO_LOCATIONS = [
    {
        "ip": "8.8.8.8",
        "country_code": "US",
        "region": "CA",
        "city": "San Francisco",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "asn_number": 15169,
        "asn_org": "Google LLC",
        "is_datacenter": True,
    },
    {
        "ip": "1.1.1.1",
        "country_code": "US",
        "region": "VA",
        "city": "Ashburn",
        "latitude": 39.0438,
        "longitude": -77.4874,
        "asn_number": 13335,
        "asn_org": "Cloudflare",
        "is_datacenter": True,
    },
    {
        "ip": "54.239.28.85",
        "country_code": "GB",
        "region": "ENG",
        "city": "London",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "asn_number": 16509,
        "asn_org": "Amazon",
        "is_datacenter": True,
    },
    {
        "ip": "45.33.32.156",
        "country_code": "DE",
        "region": "BE",
        "city": "Berlin",
        "latitude": 52.52,
        "longitude": 13.405,
        "asn_number": 63949,
        "asn_org": "Linode",
        "is_datacenter": True,
    },
    {
        "ip": "52.95.255.1",
        "country_code": "SG",
        "region": "SG",
        "city": "Singapore",
        "latitude": 1.3521,
        "longitude": 103.8198,
        "asn_number": 16509,
        "asn_org": "Amazon",
        "is_datacenter": True,
    },
]

DEMO_PATHS = ["/", "/pricing", "/checkout", "/login", "/account"]
DEMO_EVENT_TYPES = ["page_view", "click", "scroll", "form_submit", "error"]


@dataclass
class DemoSeedResult:
    tenant_id: int
    seeded_at: datetime
    expires_at: datetime
    counts: dict[str, int]


def _demo_expires_at(now: datetime) -> datetime:
    return now + timedelta(days=int(getattr(settings, "DEMO_DATA_RETENTION_DAYS", 7)))


def _select_primary_website(db: Session, tenant_id: int) -> Website | None:
    return (
        db.query(Website)
        .filter(Website.tenant_id == tenant_id, Website.deleted_at.is_(None))
        .order_by(Website.id.asc())
        .first()
    )


def _select_primary_env(db: Session, website_id: int) -> WebsiteEnvironment | None:
    return (
        db.query(WebsiteEnvironment)
        .filter(WebsiteEnvironment.website_id == website_id)
        .order_by(WebsiteEnvironment.id.asc())
        .first()
    )


def _ensure_stack_profile(db: Session, *, tenant_id: int, website_id: int) -> WebsiteStackProfile:
    profile = (
        db.query(WebsiteStackProfile)
        .filter(
            WebsiteStackProfile.tenant_id == tenant_id,
            WebsiteStackProfile.website_id == website_id,
        )
        .first()
    )
    if profile:
        return profile
    profile = WebsiteStackProfile(
        tenant_id=tenant_id,
        website_id=website_id,
        stack_type="shopify",
        confidence=0.82,
        detected_signals_json={"demo": True, "shopify_theme": True},
        manual_override=False,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _purge_demo_rows(db: Session, tenant_id: int) -> None:
    demo_tables: Iterable[tuple[type, str]] = [
        (ProtectionPreset, "is_demo"),
        (RemediationPlaybook, "is_demo"),
        (RevenueLeakEstimate, "is_demo"),
        (TrustFactorAgg, "is_demo"),
        (TrustSnapshot, "is_demo"),
        (Incident, "is_demo"),
        (GeoEventAgg, "is_demo"),
        (IPEnrichment, "is_demo"),
        (SecurityEvent, "is_demo"),
        (BehaviourEvent, "is_demo"),
        (BehaviourSession, "is_demo"),
    ]
    for model, column in demo_tables:
        field = getattr(model, column)
        db.query(model).filter(model.tenant_id == tenant_id, field.is_(True)).delete(
            synchronize_session=False
        )
    db.commit()


def purge_expired_demo_data(db: Session, *, now: datetime | None = None) -> int:
    current = now or utcnow()
    tenants = (
        db.query(Tenant)
        .filter(
            Tenant.is_demo_mode.is_(True),
            Tenant.demo_expires_at.isnot(None),
            Tenant.demo_expires_at <= current,
        )
        .all()
    )
    for tenant in tenants:
        _purge_demo_rows(db, tenant.id)
        tenant.is_demo_mode = False
        tenant.demo_seeded_at = None
        tenant.demo_expires_at = None
    db.commit()
    return len(tenants)


def seed_demo_data(
    db: Session,
    *,
    tenant_id: int,
    created_by_user_id: int | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> DemoSeedResult:
    if settings.LAUNCH_MODE:
        raise ValueError("Demo seeding is disabled in launch mode")
    current = now or utcnow()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise ValueError("Tenant not found")

    expires_at = _demo_expires_at(current)
    if tenant.is_demo_mode and tenant.demo_expires_at and tenant.demo_expires_at > current and not force:
        return DemoSeedResult(
            tenant_id=tenant_id,
            seeded_at=tenant.demo_seeded_at or current,
            expires_at=tenant.demo_expires_at,
            counts={"skipped": 1},
        )

    _purge_demo_rows(db, tenant_id)

    website = _select_primary_website(db, tenant_id)
    if not website:
        website = Website(
            tenant_id=tenant_id,
            domain="demo-store.example.com",
            display_name="Demo Storefront",
            status="active",
            created_by_user_id=created_by_user_id,
        )
        db.add(website)
        db.commit()
        db.refresh(website)

    environment = _select_primary_env(db, website.id)
    if not environment:
        environment = WebsiteEnvironment(
            website_id=website.id,
            name="production",
            base_url=f"https://{website.domain}",
            status="active",
        )
        db.add(environment)
        db.commit()
        db.refresh(environment)

    stack_profile = _ensure_stack_profile(db, tenant_id=tenant_id, website_id=website.id)

    rng = random.Random(tenant_id)
    location_payloads = []
    for location in DEMO_LOCATIONS:
        ip_hash = hash_ip(tenant_id, location["ip"])
        location_payloads.append({**location, "ip_hash": ip_hash})

    for location in location_payloads:
        enrichment = IPEnrichment(
            tenant_id=tenant_id,
            ip_hash=location["ip_hash"],
            first_seen_at=current - timedelta(hours=8),
            last_seen_at=current,
            country_code=location["country_code"],
            region=location["region"],
            city=location["city"],
            latitude=location["latitude"],
            longitude=location["longitude"],
            asn_number=location["asn_number"],
            asn_org=location["asn_org"],
            is_datacenter=location["is_datacenter"],
            source="demo",
            last_lookup_at=current,
            lookup_status="ok",
            is_demo=True,
        )
        db.add(enrichment)
    db.commit()

    behaviour_events: list[BehaviourEvent] = []
    behaviour_sessions: list[BehaviourSession] = []
    for idx in range(8):
        location = location_payloads[idx % len(location_payloads)]
        session_id = f"demo_s_{idx}"
        session_start = current - timedelta(hours=rng.randint(1, DEMO_LOOKBACK_HOURS - 1))
        event_count = rng.randint(8, 14)
        page_views = 0
        entry_path = None
        exit_path = None
        for event_idx in range(event_count):
            path = rng.choice(DEMO_PATHS)
            if entry_path is None:
                entry_path = path
            exit_path = path
            event_type = rng.choice(DEMO_EVENT_TYPES)
            if event_idx == 0:
                event_type = "page_view"
            if path == "/checkout" and event_idx % 5 == 0:
                event_type = "form_submit"
            if event_type == "page_view":
                page_views += 1
            event_ts = session_start + timedelta(minutes=event_idx * 4)
            behaviour_events.append(
                BehaviourEvent(
                    tenant_id=tenant_id,
                    website_id=website.id,
                    environment_id=environment.id,
                    ingested_at=event_ts,
                    event_ts=event_ts,
                    event_id=f"demo_evt_{idx}_{event_idx}",
                    event_type=event_type,
                    url=f"https://{website.domain}{path}",
                    path=path,
                    referrer="https://google.com" if event_idx % 3 == 0 else None,
                    session_id=session_id,
                    visitor_id=None,
                    ip_hash=location["ip_hash"],
                    user_agent="DemoBrowser/1.0",
                    meta={"is_demo": True, "sequence": event_idx},
                    is_demo=True,
                )
            )
        behaviour_sessions.append(
            BehaviourSession(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                session_id=session_id,
                started_at=session_start,
                last_seen_at=session_start + timedelta(minutes=event_count * 4),
                page_views=page_views,
                event_count=event_count,
                ip_hash=location["ip_hash"],
                entry_path=entry_path,
                exit_path=exit_path,
                country_code=location["country_code"],
                region=location["region"],
                city=location["city"],
                latitude=location["latitude"],
                longitude=location["longitude"],
                asn=location["asn_org"],
                is_datacenter=location["is_datacenter"],
                is_demo=True,
            )
        )

    db.add_all(behaviour_events)
    db.add_all(behaviour_sessions)
    db.commit()

    security_events: list[SecurityEvent] = []
    for idx in range(12):
        location = location_payloads[idx % len(location_payloads)]
        category = "threat" if idx % 3 == 0 else "login" if idx % 3 == 1 else "integrity"
        event_type = (
            "credential_stuffing"
            if category == "threat"
            else "login_attempt_failed"
            if category == "login"
            else "csp_violation"
        )
        severity = "high" if category == "threat" else "medium"
        event_time = current - timedelta(hours=rng.randint(0, DEMO_LOOKBACK_HOURS - 1))
        security_events.append(
            SecurityEvent(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                user_id=None,
                created_at=event_time,
                event_ts=event_time,
                category=category,
                event_type=event_type,
                severity=severity,
                source="demo",
                request_path="/login" if category in {"login", "threat"} else "/checkout",
                method="POST" if category in {"login", "threat"} else "GET",
                status_code=401 if category in {"login", "threat"} else 200,
                user_identifier="demo@example.com",
                session_id=None,
                client_ip=None,
                user_agent="DemoBrowser/1.0",
                ip_hash=location["ip_hash"],
                country_code=location["country_code"],
                region=location["region"],
                city=location["city"],
                latitude=location["latitude"],
                longitude=location["longitude"],
                asn_number=location["asn_number"],
                asn_org=location["asn_org"],
                is_datacenter=location["is_datacenter"],
                meta={"is_demo": True},
                is_demo=True,
            )
        )

    db.add_all(security_events)
    db.commit()

    incident_records: list[Incident] = []
    impact_records: list[ImpactEstimate] = []
    incident_templates = [
        {
            "category": "login",
            "title": "Credential stuffing surge",
            "summary": "Spike in failed logins detected on /login.",
            "severity": "high",
            "primary_country_code": "US",
            "primary_ip_hash": location_payloads[0]["ip_hash"],
            "path": "/login",
            "lost_revenue": 1400.0,
        },
        {
            "category": "integrity",
            "title": "Checkout JS errors",
            "summary": "JavaScript errors impacting checkout completion.",
            "severity": "medium",
            "primary_country_code": "GB",
            "primary_ip_hash": location_payloads[2]["ip_hash"],
            "path": "/checkout",
            "lost_revenue": 2400.0,
        },
    ]
    for template in incident_templates:
        first_seen = current - timedelta(hours=6)
        last_seen = current - timedelta(hours=1)
        impact = ImpactEstimate(
            tenant_id=tenant_id,
            website_id=website.id,
            environment_id=environment.id,
            metric_key="conversion_rate",
            incident_id=None,
            window_start=first_seen,
            window_end=last_seen,
            observed_rate=0.04,
            baseline_rate=0.08,
            delta_rate=-0.04,
            estimated_lost_conversions=32.0,
            estimated_lost_revenue=template["lost_revenue"],
            confidence=0.62,
            explanation_json={"demo": True},
        )
        db.add(impact)
        db.flush()
        impact_records.append(impact)
        incident = Incident(
            tenant_id=tenant_id,
            website_id=website.id,
            environment_id=environment.id,
            status="investigating",
            status_manual=True,
            is_demo=True,
            category=template["category"],
            title=template["title"],
            summary=template["summary"],
            severity=template["severity"],
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            primary_ip_hash=template["primary_ip_hash"],
            primary_country_code=template["primary_country_code"],
            evidence_json={
                "event_types": {"credential_stuffing": 12} if template["category"] == "login" else {"js_error": 8},
                "request_paths": {template["path"]: 10},
                "counts": {"security_events": 12},
            },
            impact_estimate_id=impact.id,
        )
        db.add(incident)
        db.flush()
        incident_records.append(incident)

    db.commit()

    for incident in incident_records:
        playbook = generate_playbook_for_incident(
            db,
            incident=incident,
            stack_profile=stack_profile,
            prescriptions=None,
        )
        if playbook:
            playbook.is_demo = True
            db.add(playbook)
            db.commit()

        presets = get_or_generate_presets(
            db,
            incident=incident,
            stack_profile=stack_profile,
            website=website,
        )
        for preset in presets:
            preset.is_demo = True
        db.commit()

    for hours_back in range(6):
        bucket = (current - timedelta(hours=hours_back)).replace(minute=0, second=0, microsecond=0)
        for location in location_payloads[:3]:
            for category in ("login", "threat", "integrity"):
                db.add(
                    GeoEventAgg(
                        tenant_id=tenant_id,
                        website_id=website.id,
                        environment_id=environment.id,
                        bucket_start=bucket,
                        event_category=category,
                        severity="high" if category == "threat" else "medium",
                        country_code=location["country_code"],
                        region=location["region"],
                        city=location["city"],
                        latitude=location["latitude"],
                        longitude=location["longitude"],
                        asn_number=location["asn_number"],
                        asn_org=location["asn_org"],
                        is_datacenter=location["is_datacenter"],
                        count=20 + hours_back * 3,
                        is_demo=True,
                    )
                )
    db.commit()

    trust_snapshots: list[TrustSnapshot] = []
    trust_factors: list[TrustFactorAgg] = []
    for hours_back in range(6):
        bucket = (current - timedelta(hours=hours_back)).replace(minute=0, second=0, microsecond=0)
        trust_snapshots.append(
            TrustSnapshot(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                bucket_start=bucket,
                path="/checkout",
                trust_score=55 - hours_back * 2,
                confidence=0.58,
                factor_count=2,
                is_demo=True,
            )
        )
        trust_snapshots.append(
            TrustSnapshot(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                bucket_start=bucket,
                path="/login",
                trust_score=60 - hours_back,
                confidence=0.6,
                factor_count=1,
                is_demo=True,
            )
        )
        trust_factors.append(
            TrustFactorAgg(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                bucket_start=bucket,
                path="/checkout",
                factor_type="js_error_spike",
                severity="medium",
                count=8 + hours_back,
                evidence_json={"demo": True, "top_error": "TypeError: undefined"},
                is_demo=True,
            )
        )
        trust_factors.append(
            TrustFactorAgg(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                bucket_start=bucket,
                path="/login",
                factor_type="credential_stuffing_detected",
                severity="high",
                count=12 + hours_back,
                evidence_json={"demo": True, "top_ip_hash": location_payloads[0]["ip_hash"]},
                is_demo=True,
            )
        )

    db.add_all(trust_snapshots)
    db.add_all(trust_factors)
    db.commit()

    leak_rows: list[RevenueLeakEstimate] = []
    for hours_back in range(6):
        bucket = (current - timedelta(hours=hours_back)).replace(minute=0, second=0, microsecond=0)
        leak_rows.append(
            RevenueLeakEstimate(
                tenant_id=tenant_id,
                website_id=website.id,
                environment_id=environment.id,
                bucket_start=bucket,
                path="/checkout",
                baseline_conversion_rate=0.08,
                observed_conversion_rate=0.04,
                sessions_in_bucket=250,
                expected_conversions=20.0,
                observed_conversions=10,
                lost_conversions=10.0,
                revenue_per_conversion=240.0,
                estimated_lost_revenue=2400.0 - hours_back * 150,
                linked_trust_score=55 - hours_back * 2,
                confidence=0.62,
                explanation_json={"demo": True, "incident_ids": [inc.id for inc in incident_records]},
                is_demo=True,
            )
        )
    db.add_all(leak_rows)
    db.commit()

    tenant.is_demo_mode = True
    tenant.demo_seeded_at = current
    tenant.demo_expires_at = expires_at
    db.commit()

    counts = {
        "behaviour_events": len(behaviour_events),
        "behaviour_sessions": len(behaviour_sessions),
        "security_events": len(security_events),
        "incidents": len(incident_records),
        "geo_event_aggs": 6 * 3 * 3,
        "trust_snapshots": len(trust_snapshots),
        "trust_factor_aggs": len(trust_factors),
        "revenue_leaks": len(leak_rows),
    }
    return DemoSeedResult(
        tenant_id=tenant_id,
        seeded_at=current,
        expires_at=expires_at,
        counts=counts,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo data for a tenant.")
    parser.add_argument("--tenant-id", type=int, required=False, help="Tenant ID to seed.")
    parser.add_argument("--force", action="store_true", help="Force reseed demo data.")
    parser.add_argument("--purge-expired", action="store_true", help="Purge expired demo data.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as db:
        if args.purge_expired:
            purge_expired_demo_data(db)
        if args.tenant_id:
            seed_demo_data(db, tenant_id=args.tenant_id, force=args.force)


if __name__ == "__main__":
    main()
