# Install the browser agent

This guide explains how to embed the APIShield browser agent and validate that events are flowing.

## Quick install

Paste the snippet in your site's `<head>` before any other scripts.

```html
{{AGENT_SNIPPET}}
```

## Validate events

1. Open your site in a new tab.
2. Trigger a page view and a click.
3. Confirm new events in **Security Events**.

## Common mistakes

- **Snippet placed after closing `</body>`**: move it into `<head>`.
- **Wrong public key**: ensure the key belongs to the selected environment.
- **Ad blockers**: some extensions may block analytics scripts.

## Single page apps

If you use React, Next.js, or Vue, ensure the snippet loads on every route. The agent listens for history changes and emits `page_view` automatically.

## Need help?

Check the troubleshooting guide for "no events showing" or contact support.
