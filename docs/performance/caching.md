# Caching Strategy v1

This document defines cache behavior for tenant-scoped dashboards and public endpoints.

## Backends

- Development: in-memory cache (`CACHE_BACKEND=memory`)
- Production: Redis (`CACHE_BACKEND=redis`, `REDIS_URL=...`)
- Disabled/chaos mode: null backend (`CACHE_BACKEND=none` or `CHAOS_CACHE_DOWN=true`)

Implementation: `backend/app/core/cache.py`

## Cache key rules

Tenant-scoped keys must include:

- `tenant_id`
- `website_id` (or `all`)
- `env_id` (or `all`)
- time range (`from`, `to`)
- filters hash
- DB scope hash (prevents cross-environment leakage)

Key helpers:

- `build_cache_key(...)`
- `build_tenant_query_cache_key(...)`
- `tenant_cache_prefix(tenant_id)`

## Internal endpoint caching (30-120s)

- `GET /api/v1/map/summary` -> `CACHE_TTL_MAP_SUMMARY`
- `GET /api/v1/map/drilldown` -> `CACHE_TTL_MAP_DRILLDOWN`
- `GET /api/v1/trust/snapshots` -> `CACHE_TTL_TRUST_SNAPSHOTS`
- `GET /api/v1/revenue/leaks` -> `CACHE_TTL_REVENUE_LEAKS`
- `GET /api/v1/portfolio/summary` -> `CACHE_TTL_PORTFOLIO_SUMMARY`
- `GET /api/v1/incidents` -> `CACHE_TTL_INCIDENTS_LIST`
- `GET /api/v1/incidents/{id}` -> `CACHE_TTL_INCIDENT_DETAIL`

## Public endpoint caching (60-300s)

- `GET /public/badge.js` -> `BADGE_JS_CACHE_SECONDS`
- `GET /public/badge/data` -> `BADGE_DATA_CACHE_SECONDS`
- `GET /public/score/v1` -> `TRUST_SCORE_CACHE_SECONDS`
- `GET /public/trust` -> `TRUST_SCORE_CACHE_SECONDS`

Public responses set `Cache-Control` and `ETag` for CDN friendliness.

## Invalidation policy

Default policy is TTL-first. Explicit invalidation is used for risky write paths:

- incident status updates
- notification rule create/update/delete
- website stack/settings updates

Helper:

- `invalidate_tenant_cache(tenant_id)` removes all keys under the tenant prefix.

## Safety guardrails

- Never cache tenant-owned data without tenant-scoped key dimensions.
- Same params with different tenant IDs must produce different keys.
- Cache reads must never bypass tenant authorization checks.

## Metrics

Prometheus metrics in `backend/app/core/metrics.py`:

- `cache_hit_total`
- `cache_miss_total`
- `cache_set_total`
- `cache_keys_set_total`
- `cache_payload_bytes`
- `cache_key_count`

These are emitted by `CacheService` on get/set/delete operations.
