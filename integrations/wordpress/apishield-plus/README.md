# APIShield Plus WordPress Plugin (v1)

## Install in 3 minutes

1) Copy the plugin folder to your WordPress install:

   `wp-content/plugins/apishield-plus`

2) Activate **APIShield Plus** in WordPress Admin > Plugins.

3) Go to **Settings > APIShield Plus** and set:

- Public key (pk_...)
- Secret key (sk_...) for server-side events
- API base URL (example: https://api.yourdomain.com)
- Agent script URL (example: https://cdn.yourdomain.com/agent.js)

4) Save settings. The plugin injects the browser agent into `<head>` and starts
   reporting login security events.

## What it sends

Browser agent (client side):
- Sends behaviour events to `/api/v1/ingest/browser` using the public key.

Server-side events (requires secret key):
- `login_attempt_failed`
- `login_attempt_succeeded`
- `brute_force` (when failed logins exceed threshold)

The plugin hashes usernames before sending (`sha256` + WordPress auth salt) and
never sends raw IP addresses.

## Configuration defaults

- Brute force threshold: 8 failed logins
- Brute force window: 300 seconds

Adjust these in **Settings > APIShield Plus**.

## Manual QA checklist

- Install plugin and activate
- Paste public key and agent URL
- Verify `/api/v1/ingest/browser` receives events
- Add secret key and trigger login failure
- Verify `/api/v1/ingest/security` receives `login_attempt_failed`
