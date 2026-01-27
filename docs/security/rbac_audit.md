# RBAC Audit Notes

This repo uses tenant-scoped RBAC via `require_role_in_tenant` and
`require_tenant_context` dependencies. The goal is to ensure every
non-public route requires authentication and applies tenant scoping.

## How to run the audit

Run the audit helper to list routes that are missing auth/RBAC guards:

```bash
python scripts/rbac_audit.py
```

If any routes are listed, they need an explicit auth or tenant dependency.

## Test helper

The test utility `assert_endpoint_requires_role` in
`backend/tests/security_utils.py` can be used to verify a route blocks
lower-privileged roles and allows the expected role.

## Public endpoints (expected)

- `/ping`
- `/api/v1/health`
- `/login`, `/register`, `/api/token` (and versioned `/api/v1/...`)
- `/openapi.json`, `/docs`
- `/metrics`
- `/api/v1/ingest/*`
- `POST /score` (telemetry, protected by Zero Trust when enabled)
- `POST /events/auth` (telemetry hook; GET requires auth)
- `GET /auth/oidc/status`, `GET /auth/oidc/start`, `GET /auth/oidc/callback`
- `GET /auth/saml/metadata`, `POST /auth/saml/acs`
