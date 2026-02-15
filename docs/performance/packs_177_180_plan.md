# Performance Packs 177-180: Discovery and File Map

This map links each prompt in packs `177`, `178`, `179`, and `180` to concrete repo paths.

## Pack 177 (Caching)

- `177.1` discovery:
  - `backend/app/core/cache.py`
  - `backend/app/core/config.py`
  - `backend/app/api/map.py`
  - `backend/app/api/trust.py`
  - `backend/app/api/revenue_leaks.py`
  - `backend/app/api/portfolio.py`
  - `backend/app/api/public_badge.py`
  - `backend/app/api/public_score.py`
- `177.2` cache service/key builder:
  - `backend/app/core/cache.py`
  - tests: `backend/tests/test_cache_strategy.py`
- `177.3` endpoint caching:
  - `backend/app/api/map.py`
  - `backend/app/api/trust.py`
  - `backend/app/api/revenue_leaks.py`
  - `backend/app/api/portfolio.py`
- `177.4` CDN headers:
  - `backend/app/api/public_badge.py`
  - `backend/app/api/public_score.py`
- `177.5` invalidation:
  - `backend/app/api/incidents.py`
  - `backend/app/api/notifications.py`
  - `backend/app/api/websites.py`
- `177.6` cache metrics:
  - `backend/app/core/metrics.py`
  - `backend/app/core/cache.py`
- `177.7` isolation tests:
  - `backend/tests/test_cache_strategy.py`
- `177.8` docs:
  - `docs/performance/caching.md`

## Pack 178 (Ingest efficiency)

- `178.1` discovery:
  - `backend/app/api/ingest.py`
  - `backend/app/api/ingest_security.py`
  - `backend/app/crud/behaviour_events.py`
  - `backend/app/crud/behaviour_sessions.py`
  - `backend/app/core/usage.py`
- `178.2` agent batching/compression/retry:
  - `agent/src/agent.js`
- `178.3` server bulk insert/upsert:
  - `backend/app/api/ingest.py`
  - `backend/app/crud/behaviour_events.py`
  - `backend/app/crud/behaviour_sessions.py`
- `178.4` sampling engine:
  - `backend/app/core/sampling.py`
  - `backend/app/api/ingest.py`
- `178.5` retention split:
  - `backend/app/crud/tenant_settings.py`
  - `backend/app/models/tenant_settings.py`
  - `backend/app/models/data_retention.py`
- `178.6` usage expansion:
  - `backend/app/core/usage.py`
  - `backend/app/models/tenant_usage.py`
  - `backend/app/api/ingest.py`
- `178.7` quota and graceful degradation:
  - `backend/app/api/ingest.py`
  - `backend/app/api/ingest_security.py`
- `178.8` backpressure visibility:
  - `backend/app/core/metrics.py`
  - `backend/app/api/ingest.py`
  - `backend/app/api/ingest_security.py`
- `178.9` docs:
  - `docs/performance/ingestion_efficiency.md`

## Pack 179 (Queue partitioning/scaling)

- `179.1` discovery:
  - `backend/app/core/queue.py`
  - `backend/app/jobs/queue_worker.py`
  - `backend/app/models/job_queue.py`
  - `backend/app/models/job_dead_letters.py`
- `179.2` job envelope:
  - `backend/app/models/job_queue.py`
  - `backend/app/core/queue.py`
  - tests: `backend/tests/test_job_queue.py`
- `179.3` queue partitions:
  - `backend/app/core/queue.py`
  - `backend/app/jobs/queue_worker.py`
- `179.4` priority scheduling:
  - `backend/app/core/queue.py`
  - tests: `backend/tests/test_job_queue.py`
- `179.5` tenant fairness:
  - `backend/app/core/queue.py`
  - `backend/app/core/rate_limit.py`
  - tests: `backend/tests/test_job_queue.py`
- `179.6` retries:
  - `backend/app/core/queue.py`
  - `backend/app/jobs/queue_worker.py`
- `179.7` DLQ:
  - `backend/app/models/job_dead_letters.py`
  - `backend/app/core/queue.py`
  - `backend/app/api/admin_queue.py`
- `179.8` observability:
  - `backend/app/core/metrics.py`
  - `backend/app/jobs/queue_worker.py`
  - `backend/app/api/admin_queue.py`
- `179.9` docs:
  - `docs/performance/queue_scaling.md`

## Pack 180 (Load/soak/chaos)

- `180.1` discovery:
  - `scripts/load/`
  - `scenarios/`
  - `docs/performance/load_tests.md`
- `180.2` event generator:
  - `scripts/load/gen_events.py`
- `180.3` load runner:
  - `scripts/load/run_load.py`
- `180.4` scenario library:
  - `scenarios/spike_1min_100k.json`
  - `scenarios/soak_6h_10k.json`
  - `scenarios/multi_tenant_fairness.json`
- `180.5` reporting:
  - `scripts/load/run_load.py`
- `180.6` chaos toggles:
  - `backend/app/core/config.py`
  - `backend/app/core/perf.py`
  - `backend/app/core/cache.py`
  - `docs/performance/chaos_drills.md`
- `180.7` thresholds:
  - `scripts/load/run_load.py`
  - scenario files in `scenarios/`
- `180.8` docs:
  - `docs/performance/load_tests.md`
  - `docs/performance/chaos_drills.md`
