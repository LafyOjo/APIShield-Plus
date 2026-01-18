# IP Data Handling

## Summary
- Raw IPs are short-lived and used only for immediate security workflows.
- Hashed IPs are retained longer for correlation inside a tenant.
- Hashing is tenant-salted to prevent cross-tenant correlation.

## What We Store
- Raw IP: `alerts.ip_address` (short-term, purgeable).
- Hashed IP: `alerts.ip_hash` (long-term correlation within a tenant).
- Future (Wave 2): coarse geo data derived from IP.

## Hashing Strategy
- Utility: `backend/app/core/privacy.py`
- `tenant_ip_salt(tenant_id)` derives a tenant-specific salt using HMAC.
- `hash_ip(tenant_id, ip_str)` uses the tenant salt + normalized IP and returns a hex digest.
- The salt is derived from `SECRET_KEY`; it is never returned to clients.

## Retention Defaults
- Raw IP retention: `tenant_settings.ip_raw_retention_days` (default: 7).
- Event retention: `tenant_settings.event_retention_days` (default: 30).
- Raw IPs should be purged earlier than event rows; hashed IPs can remain for correlation.

## Notes
- Hashes are deterministic per tenant + IP.
- The same IP hashes differently across tenants by design.
- UI can display masked IPs using `mask_ip()` without exposing raw values.
