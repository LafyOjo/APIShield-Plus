"""
Deterministic seed script for dev/demo environments.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from app.core.db import SessionLocal, Base, engine
from app.seed.utils import (
    get_or_create_api_key,
    get_or_create_membership,
    get_or_create_tenant,
    get_or_create_user,
    get_or_create_website,
    get_environment_by_name,
    seed_default_plans,
)
from app.models.alerts import Alert
from app.models.audit_logs import AuditLog
from app.models.events import Event


def ensure_not_production():
    env = os.getenv("ENV", "").lower()
    allow_prod = os.getenv("ALLOW_SEED_PROD", "0").lower() in {"1", "true", "yes"}
    if env == "production" and not allow_prod:
        print("Refusing to seed in production. Set ALLOW_SEED_PROD=1 to override.", file=sys.stderr)
        sys.exit(1)


def seed():
    ensure_not_production()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_default_plans(db)

        # Tenants
        acme = get_or_create_tenant(db, "acme", "Acme Inc")
        umbrella = get_or_create_tenant(db, "umbrella", "Umbrella Corp")

        # Users
        alice = get_or_create_user(db, "alice", "secret", role="user")
        bob = get_or_create_user(db, "bob", "secret", role="user")
        charlie = get_or_create_user(db, "charlie", "secret", role="user")

        # Memberships
        get_or_create_membership(db, alice, acme, role="owner")
        get_or_create_membership(db, bob, umbrella, role="owner")
        get_or_create_membership(db, charlie, acme, role="analyst")
        get_or_create_membership(db, charlie, umbrella, role="viewer")

        # Websites + API keys
        acme_site = get_or_create_website(db, acme, "acme-store.com")
        umbrella_site = get_or_create_website(db, umbrella, "umbrella-login.com")
        acme_env = get_environment_by_name(db, acme_site)
        umbrella_env = get_environment_by_name(db, umbrella_site)
        if acme_env and umbrella_env:
            get_or_create_api_key(
                db,
                tenant=acme,
                website=acme_site,
                environment=acme_env,
                public_key="pk_acme_active",
                raw_secret="sk_acme_active",
                name="Acme Production Key",
                revoked=False,
            )
            get_or_create_api_key(
                db,
                tenant=acme,
                website=acme_site,
                environment=acme_env,
                public_key="pk_acme_revoked",
                raw_secret="sk_acme_revoked",
                name="Acme Revoked Key",
                revoked=True,
            )
            get_or_create_api_key(
                db,
                tenant=umbrella,
                website=umbrella_site,
                environment=umbrella_env,
                public_key="pk_umbrella_active",
                raw_secret="sk_umbrella_active",
                name="Umbrella Production Key",
                revoked=False,
            )
            get_or_create_api_key(
                db,
                tenant=umbrella,
                website=umbrella_site,
                environment=umbrella_env,
                public_key="pk_umbrella_revoked",
                raw_secret="sk_umbrella_revoked",
                name="Umbrella Revoked Key",
                revoked=True,
            )

        # Events / alerts / audit logs (simple demo data)
        now = datetime.now(timezone.utc)
        demo_events = [
            Event(tenant_id=acme.id, username="alice", action="login", success=True, timestamp=now),
            Event(tenant_id=umbrella.id, username="bob", action="login", success=True, timestamp=now),
            Event(tenant_id=acme.id, username="charlie", action="login", success=False, timestamp=now),
        ]
        for ev in demo_events:
            db.merge(ev)

        demo_alerts = [
            Alert(ip_address="10.0.0.1", total_fails=3, detail="Acme suspicious"),
            Alert(ip_address="10.0.0.2", total_fails=5, detail="Umbrella block"),
        ]
        for al in demo_alerts:
            db.merge(al)

        demo_audit = [
            AuditLog(tenant_id=acme.id, username="alice", event="user_login_success", timestamp=now),
            AuditLog(tenant_id=umbrella.id, username="bob", event="user_login_success", timestamp=now),
        ]
        for au in demo_audit:
            db.merge(au)

        db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    seed()
