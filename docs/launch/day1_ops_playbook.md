# Day-1 Ops Playbook

Purpose
- Provide a repeatable, low-drama operating rhythm for launch and day-1 production.
- Define how to detect issues, respond, communicate, and recover.

Launch mode posture
- Set `LAUNCH_MODE=true` in production.
- Verify demo-only behavior is disabled (no demo seeding, no demo data included in responses).
- Ensure billing enforcement is strict (hard limits and paywall gating enabled).
- Confirm `ENVIRONMENT=production` and `SECURITY_HEADERS_ENABLED=true`.

Required secrets checklist (fail fast)
- `SECRET_KEY`
- `DATABASE_URL`
- `INTEGRATION_ENCRYPTION_KEY`
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` (if billing is enabled)
- `ZERO_TRUST_API_KEY` (if Zero Trust mode is enabled)
- `SSO` secrets if SSO is enabled

Daily health checks (owner or on-call)
- API health: `/api/v1/health` returns 200
- Ingest health: `/api/v1/ingest/browser` success rate is stable
- Job health: geo enrichment, aggregation, exports (no backlog spikes)
- Error rates: 5xx rates within normal baseline
- Rate-limit metrics: 429 spikes investigated
- DB health: connection pool saturation and slow queries
- Status page: reflect current platform health

Abuse and safety checks
- Review IP hash banlist for suspicious spikes
- Confirm ingest RPM limits are enforced per plan
- Check audit log for admin/support access

Support workflow (daily)
- Triage new incidents and security events
- Respond to support tickets with tenant context
- Use support view-as only with a reason and log it

Backup and rollback readiness
- Ensure daily backups are enabled (DB + object storage)
- Validate restore procedure once per month
- Keep last known good deployment artifact

Incident response (quick guide)
1) Identify impact: API, ingest, geo, notifications, dashboard
2) Set severity and publish status page incident
3) Mitigate (roll back, disable feature, reduce load)
4) Communicate status updates every 30-60 minutes
5) Resolve and verify recovery metrics
6) Write post-incident report within 48 hours

Mock incident drill (monthly)
- Scenario: ingest outage (5xx for ingest endpoints)
- Step 1: simulate by blocking ingress or toggling a test failure flag
- Step 2: verify alerting detects elevated error rates
- Step 3: publish status incident (investigating -> identified)
- Step 4: apply mitigation (rollback or hotfix)
- Step 5: update status to monitoring then resolved
- Step 6: document timeline and lessons learned

Post-incident report template (required fields)
- Summary and customer impact
- Root cause
- Detection and response timeline
- Mitigation steps
- Preventative actions

Contacts
- Primary on-call: <fill>
- Secondary on-call: <fill>
- Status page admin: <fill>
- Security contact: <fill>
