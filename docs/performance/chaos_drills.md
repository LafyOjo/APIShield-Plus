# Chaos Drills

Run these drills in staging after load tests to validate recovery and isolation.

## Drill 1: DB latency spike

Goal: confirm ingest stays responsive and backlog drains.

Steps:
1) Inject DB latency using `CHAOS_DB_LATENCY_MS=200` (or via your DB proxy).
2) Run `scenarios/spike_1min_100k.json`.
3) Observe ingest error rate and queue depth.
4) Remove latency; confirm backlog drains.

Success:
- Error rate stays under 1%.
- Queue depth returns to baseline within 10 minutes.

## Drill 2: Queue worker crash

Goal: verify resilience to worker failures.

Steps:
1) Start `queue_worker` for critical and bulk queues.
2) Kill the bulk worker mid-run.
3) Confirm critical queue continues to drain.
4) Restart bulk worker and confirm backlog drains.

Success:
- Critical queue latency remains stable.
- Bulk queue recovers without manual intervention.

## Drill 3: Redis outage (if Redis cache/queue is enabled)

Goal: confirm graceful fallback.

Steps:
1) Disable Redis or set `CHAOS_CACHE_DOWN=true` to force cache fallback.
2) Run a moderate load scenario.
3) Validate that cache misses are handled without errors.

Success:
- Read endpoints still respond.
- Cache metrics reflect fallback behavior.

## Drill 4: Partial ingest failures

Goal: confirm per-tenant isolation.

Steps:
1) Revoke one tenant's API key during a multi-tenant run.
2) Ensure other tenants continue to ingest.
3) Confirm invalid attempts are rate limited.

Success:
- Only revoked tenant shows elevated errors.
- No cross-tenant impact.
