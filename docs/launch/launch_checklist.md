# Launch Readiness Checklist

Use this checklist before taking production traffic or payment.

Launch mode
- [ ] `LAUNCH_MODE=true` in production
- [ ] Demo seeding disabled and demo data not included in responses
- [ ] `ENVIRONMENT=production`

Legal and privacy
- [ ] Privacy policy covers IP hashing and retention windows
- [ ] Cookie notice for dashboard and marketing site (if needed)
- [ ] DPA template available for enterprise

Security
- [ ] All secrets configured in env vars (no hardcoded secrets)
- [ ] Encryption key set (`INTEGRATION_ENCRYPTION_KEY`)
- [ ] Security headers enabled (HSTS, CSP, X-Frame-Options)
- [ ] Rate limits verified on ingest endpoints
- [ ] RBAC checks enforced for all routes

Monitoring
- [ ] Health checks configured for API and ingest
- [ ] Error rate alerts configured
- [ ] Job queues monitored (geo enrichment, aggregation, exports)
- [ ] Status page live and tested

Support readiness
- [ ] Admin console access limited to platform admins
- [ ] Support view-as audited and reason required
- [ ] Standard "data not showing" playbook ready

Billing
- [ ] Stripe keys configured and webhook verified
- [ ] Checkout flow tested end-to-end
- [ ] Plan entitlements match pricing page
- [ ] Failed payment handling documented

Deployment and rollback
- [ ] Migrations tested (upgrade, downgrade)
- [ ] Rollback plan tested in staging
- [ ] Staging mirrors production settings

Incident response
- [ ] Severity definitions documented
- [ ] Status incident workflow practiced
- [ ] Mock incident drill completed

Mock incident drill runbook
- [ ] Simulate ingest outage
- [ ] Verify alerts trigger
- [ ] Publish status incident
- [ ] Recover and close incident
- [ ] Post-incident report completed
