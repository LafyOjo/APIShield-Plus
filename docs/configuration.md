# Configuration Guide

## Required keys
- `DATABASE_URL`: database connection string.
- `SECRET_KEY`: JWT/signing secret.
- `ENVIRONMENT`: environment label (development, staging, production).

## Recommended defaults for development
- `TENANT_HEADER_NAME=X-Tenant-ID`
- `REQUIRE_TENANT_HEADER=true`
- `TENANT_CONTEXT_RESOLUTION_ORDER=["header","jwt","default"]`
- `DEFAULT_TENANT_SLUG=` (leave empty to force explicit tenant selection)
- `ALLOW_MULTI_TENANT_DEV_BYPASS=false`
- `TENANT_STRICT_404=true`
- `INVITE_TOKEN_TTL_HOURS=72`
- `AUDIT_WS_REQUIRE_TENANT=true`
- Existing app defaults: `FAIL_LIMIT=5`, `FAIL_WINDOW_SECONDS=60`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`
- For SSO dev flows: `FRONTEND_BASE_URL=http://localhost:3000`, `SSO_STATE_TTL_SECONDS=600`
- Multi-region readiness: `DEFAULT_TENANT_REGION=us`
- Optional platform audit anchor: `PLATFORM_AUDIT_TENANT_ID=1`

## Production guidance
- Keep `REQUIRE_TENANT_HEADER=true` and `TENANT_STRICT_404=true` to avoid leakage.
- Do not set `DEFAULT_TENANT_SLUG` in production; require explicit tenant selection.
- Keep `ALLOW_MULTI_TENANT_DEV_BYPASS=false`.
- Use a short `INVITE_TOKEN_TTL_HOURS` if invites are sensitive; 72 is the baseline.
- If adjusting `TENANT_CONTEXT_RESOLUTION_ORDER`, prefer `header` first and avoid adding fallback defaults unless required.
- Ensure `AUDIT_WS_REQUIRE_TENANT=true` so websockets stay scoped.
- Set `SECURITY_HEADERS_ENABLED=true` and configure CSP/HSTS for your dashboard domain.
- For SSO: set `FRONTEND_BASE_URL` to your dashboard origin and keep `SSO_STATE_TTL_SECONDS` short.
- If you plan for data residency, configure `REGION_DB_URLS` and `REGION_EXPORT_TARGETS` as JSON maps.
- If you want platform-admin actions to show in audit logs, set `PLATFORM_AUDIT_TENANT_ID` to a real tenant id.

## Notes
- All settings load via `app.core.config.Settings` (Pydantic BaseSettings). `.env` or environment variables override code defaults.
- Lists (e.g., `TENANT_CONTEXT_RESOLUTION_ORDER`) should be provided as JSON arrays.
- Region maps (e.g., `REGION_DB_URLS`) should be provided as JSON objects.
