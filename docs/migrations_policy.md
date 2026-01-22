# Database Migration Policy

This policy is required for all schema changes. The goal is zero downtime,
reversible migrations, and predictable release sequencing.

## Core rules

- Prefer additive migrations first. New columns are nullable by default.
- Do not remove or rename columns in the same release as the additive change.
- Avoid data backfills inside Alembic migrations. Use background jobs instead.
- If a NOT NULL or constraint is required, apply it in a later migration after
  the backfill and dual-write period.
- Every migration must be reversible unless explicitly documented.

## Zero-downtime patterns

1) Add columns as nullable (or with safe defaults).
2) Dual-write: write to both old and new columns during the transition.
3) Read-fallback: read new column, fall back to old column if null/missing.
4) Backfill in the background with progress tracking.
5) Flip reads to the new column only after backfill is complete.
6) Enforce NOT NULL/constraints and remove old fields in a later release.

## Backfill framework

Backfill jobs live under `backend/app/jobs/backfills/`. Each job should record
progress in the `backfill_runs` table:

- `job_name`
- `started_at`
- `finished_at`
- `last_id_processed`

Jobs must be resumable and idempotent. Use `resume_or_start_backfill()` and
`record_backfill_progress()` from `backend/app/jobs/backfills/base.py`.

## Release sequencing

1) Deploy additive migrations (nullable columns, new tables).
2) Deploy code that writes to the new fields (dual-write).
3) Run backfill job(s) until complete.
4) Deploy code that reads only the new fields.
5) Apply constraint/cleanup migrations (NOT NULL, drop old columns).

## Migration validation

CI must validate:

- `alembic upgrade head` on a fresh DB
- `alembic downgrade -1` (optional but recommended)

Manual smoke test:

```
python scripts/migration_smoke_test.py
```

## Rollback discipline

- Rollbacks should be done via `alembic downgrade` or by deploying the prior
  application version compatible with the current schema.
- Avoid irreversible migrations. If unavoidable, document the risk and the
  fallback plan in the PR.
