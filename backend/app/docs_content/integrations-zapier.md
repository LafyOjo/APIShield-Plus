# Zapier & webhook recipes

Connect incidents and verification results to automation flows.

## Example webhook

```http
POST https://hooks.zapier.com/hooks/catch/...
Content-Type: application/json

{
  "event": "incident_opened",
  "tenant": "acme",
  "severity": "high"
}
```

## Tips

- Add rate limits to avoid duplicate alerts.
- Use the incident `id` to dedupe workflows.
