# Queue Partitioning and Worker Scaling

Queue architecture is implemented in:

- `backend/app/core/queue.py`
- `backend/app/jobs/queue_worker.py`
- `backend/app/api/admin_queue.py`

## Queue partitions

- `critical`: notification send, incident updates
- `standard`: trust scoring, revenue leak jobs
- `bulk`: geo enrichment backfills, data exports, marketplace seed

Workers can be pinned to a single queue:

```bash
python -m app.jobs.queue_worker --queue critical
python -m app.jobs.queue_worker --queue standard
python -m app.jobs.queue_worker --queue bulk
```

Or run all queues in one process:

```bash
python -m app.jobs.queue_worker --queue all
```

## Fairness controls

Per-tenant throttles are applied by queue type:

- standard queue:
  - `QUEUE_TENANT_RPM_STANDARD`
  - `QUEUE_TENANT_BURST_STANDARD`
  - `QUEUE_TENANT_MAX_IN_FLIGHT_STANDARD`
- bulk queue:
  - `QUEUE_TENANT_RPM_BULK`
  - `QUEUE_TENANT_BURST_BULK`
  - `QUEUE_TENANT_MAX_IN_FLIGHT_BULK`

When throttled, jobs are delayed by updating `run_at`; they are not dropped.

## Retry policies

Defined in `JOB_RETRY_POLICIES`:

- critical jobs retry faster with lower delay caps
- bulk jobs retry slower with larger delay windows

After max attempts, jobs are moved to dead-letter storage.

## Dead-letter queue

Persistent model: `job_dead_letters`

Admin endpoint:

- `GET /api/v1/admin/queue/dead-letters`

## Queue observability

Prometheus metrics:

- `queue_depth`
- `queue_job_total`
- `queue_retry_total`
- `queue_wait_seconds`
- `queue_run_seconds`

Admin endpoint:

- `GET /api/v1/admin/queue/stats`

Returns per queue:

- `queued`, `running`
- `succeeded_last_hour`, `failed_last_hour`
- `retrying`
- `avg_queue_age_seconds`
- `dead_letters_total`

## Operational checklist

1. If `critical` queue depth grows, scale critical workers first.
2. If `bulk` backlog grows, scale bulk workers without affecting critical capacity.
3. If dead letters spike, inspect `/api/v1/admin/queue/dead-letters` and requeue fixed jobs.
4. Watch fairness counters during tenant bursts to ensure no single tenant starvation.
