# SAML Setup (Scaffold)

This doc captures the minimum SAML fields required to store tenant SSO
settings and generate Service Provider (SP) metadata. The ACS flow is
stubbed for now and will be completed when SAML login is implemented.

## Required fields

For provider `saml`, the config must include:

- `idp_entity_id` (IdP issuer/entity ID)
- `idp_sso_url` (IdP SSO URL)
- `idp_x509_cert` (IdP signing certificate, PEM or base64)
- `sp_entity_id` (SP entity ID)
- `sp_acs_url` (SP Assertion Consumer Service URL)

Optional:

- `sp_x509_cert` (SP signing certificate, if you sign requests/assertions)
- `allowed_email_domains` (optional domain allowlist)
- `sso_required` (enforce SSO-only login)

## SP metadata endpoint

Use the tenant-specific metadata endpoint to configure your IdP:

```
GET /auth/saml/metadata?tenant_id=<tenant_slug_or_id>
```

The response is XML metadata containing:

- `EntityDescriptor` (SP entity ID)
- `AssertionConsumerService` (ACS URL)
- Optional signing certificate

## Configuration flow (API)

Configure SAML via the SSO config endpoint:

```
POST /api/v1/sso/config
```

Payload example:

```json
{
  "provider": "saml",
  "is_enabled": true,
  "idp_entity_id": "https://idp.example.com/entity",
  "idp_sso_url": "https://idp.example.com/sso",
  "idp_x509_cert": "-----BEGIN CERTIFICATE-----\\n...\\n-----END CERTIFICATE-----",
  "sp_entity_id": "https://api.example.com/saml/metadata",
  "sp_acs_url": "https://api.example.com/auth/saml/acs",
  "sp_x509_cert": null,
  "allowed_email_domains": ["example.com"],
  "sso_required": false,
  "auto_provision": false
}
```

## Notes

- The ACS endpoint is a placeholder and currently returns `501 Not Implemented`.
- Signature validation and user provisioning rules will be enforced when
  SAML login is fully implemented.
