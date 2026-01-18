# Backfill Default Tenant for Legacy Data

## Purpose
Legacy deployments used global users/events/logs with no tenant. This backfill creates a
single "Default Workspace" tenant and attaches existing users and legacy rows so the
system remains usable after multi-tenancy is enabled.

## When to run
- After running the migrations that introduce tenants and memberships.
- On a database that previously ran in single-tenant mode.

## What the script does
- Creates a tenant named "Default Workspace" with slug "default" if no tenants exist.
- Assigns memberships for all existing users.
  - Owner: first admin user by id (or first user if no admin exists).
  - Others: admin -> admin, everything else -> viewer.
- Fills `tenant_id` for legacy tables if the column exists:
  - `alerts`, `events`, `audit_logs`, `access_logs`, `auth_events`
- Skips if multiple tenants already exist (assumes already migrated).
- Skips if a single non-default tenant exists (requires manual decision).
- Safe to re-run (idempotent).

## Usage
Set your environment and run:

```bash
python scripts/upgrade_to_multitenant.py
```

Required environment variables:
- `DATABASE_URL`
- `SECRET_KEY`

## Notes
- If you already created a tenant manually (slug not "default"), the script will not
  modify anything. Decide whether to rename the tenant or migrate memberships manually.
- If you add `tenant_id` columns to additional legacy tables, update the script's
  `LEGACY_TABLES` list before re-running.
