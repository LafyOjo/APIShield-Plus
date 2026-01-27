# Webhook verification

APIShield webhooks include a signature so you can verify authenticity.

## Steps

1. Read the request body as raw bytes.
2. Compute an HMAC using your shared secret.
3. Compare the result to the `X-ApiShield-Signature` header.

```text
signature = hmac_sha256(secret, raw_body)
```

## Tips

- Compare signatures using constant-time comparison.
- Reject requests older than your allowed timestamp window.
