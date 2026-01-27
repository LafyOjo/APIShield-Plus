# Key Rotation Plan (Draft)

This document outlines the staged key rotation plan for APIShield+.

## Goals

- Support regular key rotation without downtime.
- Keep audit logs and historical data readable.
- Avoid leaking secrets during rotation.

## Keys Covered

- `SECRET_KEY` (JWT signing)
- `INTEGRATION_ENCRYPTION_KEY` (external integrations config encryption)
- Stripe webhook signing secret
- Future: per-tenant signing keys (if introduced)

## Rotation Strategy

1) **Dual-key phase (grace period)**
   - Introduce a new key as the primary.
   - Keep the previous key as a secondary for verification/decryption.
   - Configure the app to accept both keys (primary for write, secondary for read).

2) **Cutover**
   - Update all services to use the new key for issuing tokens or encrypting new data.
   - Validate that all traffic uses the new key for minting.

3) **Retirement**
   - Remove the old key after the grace period.
   - Confirm no active tokens or encrypted payloads depend on it.

## Implementation Notes

- JWT rotation should support a short overlap (e.g., 24-72 hours).
- Encryption key rotation should keep both keys available until all secrets
  are re-encrypted or aged out.
- For Stripe, rotate webhook signing secrets via Stripe dashboard and update
  the environment variable in a controlled rollout.

## Audit Requirements

- Log every key rotation event with timestamp and actor (if known).
- Keep a record of key identifiers, not the raw secrets.

## Next Steps

- Add configuration support for multiple active keys.
- Add a management command to re-encrypt integration secrets.
- Add monitoring to detect token failures tied to retired keys.
