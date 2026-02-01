# Cloudflare rules

Apply WAF and rate-limit rules that match your active incidents.

## Recommended starter rule

```yaml
# Block aggressive login storms
- expression: (http.request.uri.path contains "/login") and ip.src.rate > 100
  action: block
```

## Checklist

- Apply rules in **Report Only** mode first.
- Confirm suspicious requests drop in the Security Events table.
- Promote to block once verified.
