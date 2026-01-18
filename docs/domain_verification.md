# Domain Verification

This document describes how tenants can prove domain ownership before enabling
security features or trusting inbound signals.

## Verification methods

### Meta tag
Add this tag to the `<head>` of your homepage:

```
<meta name="api-shield-verification" content="YOUR_TOKEN_HERE">
```

### Well-known file
Create a file at:

`https://your-domain.com/.well-known/api-shield-verification.txt`

File contents:

```
YOUR_TOKEN_HERE
```

### DNS TXT
Create a TXT record:

`_api-shield-verification.your-domain.com`

Value:

```
YOUR_TOKEN_HERE
```

## API usage

Start verification:

`POST /api/v1/websites/{website_id}/verify/start`

Check verification status:

`GET /api/v1/websites/{website_id}/verify/status`

Check verification (manual in dev):

`POST /api/v1/websites/{website_id}/verify/check`
