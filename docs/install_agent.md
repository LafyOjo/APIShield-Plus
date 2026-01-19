# Browser Agent v1

## Quick install

1) Host the agent file from `agent/dist/agent.js` on your CDN or app domain.

2) Add the snippet to your site:

```html
<script>
  window.__API_SHIELD_KEY__ = "pk_your_public_key";
  window.__API_SHIELD_INGEST_URL__ = "https://api.yourdomain.com/api/v1/ingest/browser";
</script>
<script async src="https://cdn.yourdomain.com/agent.js" data-key="pk_your_public_key"></script>
```

You can also pass the key and endpoint directly on the script tag:

```html
<script
  async
  src="https://cdn.yourdomain.com/agent.js"
  data-key="pk_your_public_key"
  data-endpoint="https://api.yourdomain.com/api/v1/ingest/browser"
></script>
```

## Build the agent

The agent build supports a build-time ingest URL override via `AGENT_INGEST_URL`:

```bash
cd agent
AGENT_INGEST_URL="https://api.yourdomain.com/api/v1/ingest/browser" npm run build
```

Output:

- `agent/dist/agent.js`

## Captured events

The v1 agent emits:

- `page_view` (initial load + SPA navigation)
- `click` (tag, id, classes only)
- `scroll` (max depth, throttled)
- `form_submit` (form id/name/action, no field values)
- `error` (message, source, line, column, truncated)

No keystrokes or form field values are collected by default.

## Local dev

Serve the agent file locally:

```bash
cd agent
npm run build
python -m http.server 8082
```

Then reference:

```
http://localhost:8082/dist/agent.js
```
