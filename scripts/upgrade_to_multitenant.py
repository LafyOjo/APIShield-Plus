"""
Backfill legacy data into a default tenant after enabling multi-tenancy.

Creates "Default Workspace" (slug "default") when no tenants exist, assigns
memberships for existing users, and fills tenant_id on legacy tables if the
column exists. Safe to re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys
from typing import Iterable

from sqlalchemy import MetaData, Table, inspect, update
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_TENANT_NAME = "Default Workspace"
DEFAULT_TENANT_SLUG = "default"
LEGACY_TABLES = (
    "alerts",
    "events",
    "audit_logs",
    "access_logs",
    "auth_events",
)


@dataclass(frozen=True)
class BackfillResult:
    tenant_id: int | None
    created_tenant: bool
    memberships_created: int
    tenant_updates: dict[str, int]
    skipped: bool
    reason: str | None


def _ensure_env() -> None:
    missing = []
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if not os.getenv("SECRET_KEY"):
        missing.append("SECRET_KEY")
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)


def _select_owner(users: Iterable["User"]) -> "User | None":
    for user in users:
        if user.role == "admin":
            return user
    return next(iter(users), None)


def _map_membership_role(user_role: str) -> str:
    if user_role == "admin":
        return "admin"
    return "viewer"


def _update_tenant_ids(db: Session, tenant_id: int) -> dict[str, int]:
    engine = db.get_bind()
    inspector = inspect(engine)
    metadata = MetaData()
    updates: dict[str, int] = {}
    for table_name in LEGACY_TABLES:
        if not inspector.has_table(table_name):
            continue
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            continue
        table = Table(table_name, metadata, autoload_with=engine)
        stmt = update(table).where(table.c.tenant_id.is_(None)).values(tenant_id=tenant_id)
        result = db.execute(stmt)
        updates[table_name] = int(result.rowcount or 0)
    if updates:
        db.commit()
    return updates


def backfill_default_tenant(
    db: Session,
    *,
    default_name: str = DEFAULT_TENANT_NAME,
    default_slug: str = DEFAULT_TENANT_SLUG,
) -> BackfillResult:
    from app.crud.memberships import create_membership
    from app.crud.tenants import create_tenant
    from app.models.memberships import Membership
    from app.models.tenants import Tenant
    from app.models.users import User

    tenants = db.query(Tenant).order_by(Tenant.id).all()
    if len(tenants) > 1:
        return BackfillResult(
            tenant_id=None,
            created_tenant=False,
            memberships_created=0,
            tenant_updates={},
            skipped=True,
            reason="Multiple tenants already exist; backfill skipped.",
        )

    if len(tenants) == 1 and tenants[0].slug != default_slug:
        return BackfillResult(
            tenant_id=None,
            created_tenant=False,
            memberships_created=0,
            tenant_updates={},
            skipped=True,
            reason=f"Existing tenant slug is '{tenants[0].slug}', not '{default_slug}'.",
        )

    created_tenant = False
    if not tenants:
        tenant = create_tenant(db, name=default_name, slug=default_slug)
        created_tenant = True
    else:
        tenant = tenants[0]

    users = db.query(User).order_by(User.id).all()
    memberships = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant.id)
        .all()
    )
    membership_user_ids = {membership.user_id for membership in memberships}
    has_owner = any(
        membership.role == "owner" and membership.status == "active"
        for membership in memberships
    )

    memberships_created = 0
    owner_user = None
    if not has_owner and users:
        owner_user = _select_owner(users)
        if owner_user is not None:
            existed = owner_user.id in membership_user_ids
            create_membership(
                db,
                tenant_id=tenant.id,
                user_id=owner_user.id,
                role="owner",
                created_by_user_id=owner_user.id,
                status="active",
            )
            if not existed:
                memberships_created += 1
            membership_user_ids.add(owner_user.id)

    for user in users:
        if user.id in membership_user_ids:
            continue
        role = _map_membership_role(user.role)
        create_membership(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            role=role,
            created_by_user_id=owner_user.id if owner_user else None,
            status="active",
        )
        memberships_created += 1

    tenant_updates = _update_tenant_ids(db, tenant.id)

    return BackfillResult(
        tenant_id=tenant.id,
        created_tenant=created_tenant,
        memberships_created=memberships_created,
        tenant_updates=tenant_updates,
        skipped=False,
        reason=None,
    )


def main() -> None:
    _ensure_env()
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = backfill_default_tenant(db)

    if result.skipped:
        print(f"Backfill skipped: {result.reason}")
        return

    tenant_status = "created" if result.created_tenant else "existing"
    print(f"Default tenant {tenant_status} with id={result.tenant_id}")
    print(f"Memberships created: {result.memberships_created}")
    if result.tenant_updates:
        for table_name, count in result.tenant_updates.items():
            print(f"Updated {count} rows in {table_name}")
    else:
        print("No legacy tenant_id updates applied.")


if __name__ == "__main__":
    main()
