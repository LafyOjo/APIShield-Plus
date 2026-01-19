# Geo Map Feature Gating

The geo map views are plan-gated and privacy-aware from day one. This keeps
geo insights useful while respecting customer privacy and plan boundaries.

## Entitlements

- Feature flag: `features.geo_map`
- Limits:
  - `limits.geo_history_days`
  - `limits.raw_ip_retention_days`

## Behavior

- If `features.geo_map` is disabled:
  - `/api/v1/security/locations` and `/api/v1/security/ips` are limited to the
    last 24 hours.
  - Only country-level location rollups are returned.
- If `features.geo_map` is enabled:
  - Requested time windows are clamped to `limits.geo_history_days`.
  - Raw IPs are never returned unless:
    - `ALLOW_RAW_IP_SECURITY_ENDPOINTS=true`
    - caller role is `owner` or `admin`
    - data falls within the effective raw IP retention window

## Retention Defaults

`TenantSettings.ip_raw_retention_days` defaults to the plan limit
`limits.raw_ip_retention_days` when a tenant is created.

## Plan Guidance

- Free: geo history limited to 1 day, no raw IP exposure.
- Pro/Business: longer geo history windows with raw IP access gated by role
  and retention rules.
