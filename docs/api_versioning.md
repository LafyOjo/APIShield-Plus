# API Versioning Policy

## Style
- Path-based versioning.
- Dashboard/auth endpoints live under `/api/v1/...`.
- Ingestion endpoints (future) live under `/ingest/v1/...`.

## Prefix constants
- `API_PREFIX = /api`
- `API_VERSION = v1`
- `API_V1_PREFIX = /api/v1`
- `INGEST_V1_PREFIX = /ingest/v1`

## Rules
- All new endpoints ship under `/api/v1`.
- Backwards compatibility may be provided via legacy prefixes (`/api` and existing paths) during Section 1; deprecated paths should return warnings in docs and be removed in the next major bump.
- Public ingestion routes stay separate from dashboard/auth routes to allow different auth, rate limits, and scaling.

## When to bump versions
- Breaking request/response shape changes.
- Authentication or authorization model changes that break existing clients.
- Deprecating fields that clients rely on without a compatibility shim.
- Adding required headers/params without defaults.

## Deprecation process
- Announce deprecation in docs and changelog.
- Keep legacy routes available for at least one minor cycle when feasible.
- Add automated tests to ensure both versioned and legacy paths behave during the transition.
- Remove legacy routes in the next major version (v2) after notice.

## Breaking definitions
- Dashboard endpoints: any change that prevents existing UI/SDKs from functioning without code changes.
- Ingestion endpoints: any schema or auth change that rejects previously accepted payloads or alters response semantics.

## Implementation notes
- Backend constants live in `app/core/versioning.py`.
- Routers are mounted under `/api/v1` (canonical) plus `/api` and legacy roots for temporary compatibility.
- Frontend defaults to calling `/api/v1/...` automatically via `apiFetch` path normalization.
- Health endpoint available at `/api/v1/health`.

## Tests
- Add integration tests for `/api/v1/health` and at least one legacy-compatible path to ensure mounting is correct.
