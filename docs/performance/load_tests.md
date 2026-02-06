# Load Testing Toolkit

This repo ships a lightweight ingest load harness to validate spike, soak, and multi-tenant fairness scenarios.

## Scripts

- `scripts/load/gen_events.py`: event generator helpers
- `scripts/load/run_load.py`: async load runner with scenario configs

## Scenario format

Each scenario JSON contains:

- `name`
- `base_url` (ingest host)
- `ingest_path` (default `/api/v1/ingest/browser`)
- `workers` (process count)
- `batch_size` (events per request)
- `max_in_flight` (per worker concurrency)
- `segments`: list of `{duration_seconds, rps}` where `rps` is events/sec
- `targets`: list of `{api_key, domain, weight}`
- optional `event_mix`, `path_pool`, `session_pool_size`
- optional `security_ingest_path` (defaults to `/api/v1/ingest/integrity`)
- optional `security_auth_header` (defaults to `X-Api-Key`)
- optional `metrics_path` (defaults to `/metrics`)
- optional `drain_check` block for backlog drain validation

`event_mix` can include security types like `login_attempt_failed` and `csp_violation`.
- `output_json` + `output_md` for reports

## Example runs

```bash
python scripts/load/run_load.py --scenario scenarios/spike_1min_100k.json
python scripts/load/run_load.py --scenario scenarios/soak_6h_10k.json
python scripts/load/run_load.py --scenario scenarios/multi_tenant_fairness.json
```

Use `--base-url` to override the scenario URL for staging.

## Output artifacts

- JSON report with per-worker stats + merged summary
- Markdown summary with thresholds
- Metrics snapshot with queue depth and slow query delta (if available)

Slow query metrics require `PERF_PROFILING=true` on the API.

## Pass/Fail thresholds (default)

- Error rate < 0.5%
- Ingest p99 < 500ms

Tune thresholds in the report or update the summary logic in `scripts/load/run_load.py`.
