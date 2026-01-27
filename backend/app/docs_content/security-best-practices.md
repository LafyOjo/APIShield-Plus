# Security best practices

These defaults reduce risk without breaking your site.

## CSP (Content Security Policy)

- Start in **report-only** mode.
- Allow only trusted script sources.
- Review violation reports weekly.

## Rate limits

- Add per-IP limits for `/login` and `/checkout`.
- Use burst limits for short spikes.

## Account protections

- Require MFA for admin users.
- Lock accounts after repeated failed logins.

## Incident workflow

- Document the "who/what/when" for each incident.
- Apply playbooks and record verification results.
