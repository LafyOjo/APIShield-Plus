# Secure Defaults

This document summarizes the baseline security defaults for the APIShield+ app.

## Sessions and tokens

- Access tokens are short-lived by default (`ACCESS_TOKEN_EXPIRE_MINUTES=15`).
- Refresh tokens are not implemented yet; clients should re-auth on expiry.
- Token-based auth uses Authorization headers, not cookies.

## CSRF

- CSRF protections are not required for header-based bearer tokens.
- If cookie-based auth is introduced, add CSRF tokens and `SameSite` cookie
  settings before enabling it in production.

## Response hardening

- Security headers are injected by middleware (CSP, HSTS, etc.).
- Sensitive fields are excluded from API responses by default.
