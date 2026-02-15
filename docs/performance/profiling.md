# Profiling and Benchmarks

This repo includes opt-in profiling to track request latency, DB time, and slow
query fingerprints, plus a repeatable benchmark runner for API baselines.

## Enable profiling

Set the environment flags:

```
PERF_PROFILING=true
PERF_SLOW_QUERY_MS=200
PERF_SLOW_QUERY_MAX_PER_REQUEST=5
```

Set `PERF_SLOW_QUERY_MS=0` to log every query (useful for deep dives).

When enabled, request logs include:

- `duration_ms`
- `db_time_ms`, `db_queries_count`
- `handler_time_ms`, `serialize_time_ms`
- `slow_queries` (fingerprints only, capped per request)

Slow queries are logged separately as `db.slow_query` events with a sanitized
fingerprint (no literal values).

## Frontend timings

The dashboard records lightweight timings in `frontend/src/perf.js`:

- `ttfb_ms`
- `dom_content_loaded_ms`
- `fcp_ms`
- `dashboard_ready_ms`
- `map_summary_loaded_ms`

Use these to spot frontend regressions alongside API benchmarks.

## Benchmark runner

Run a repeatable API sweep with JSON + Markdown output:

```
python scripts/perf/bench.py --base-url http://localhost:8000 --report-dir ./perf_reports
```

Use `--smoke` for a fast health-only sweep (CI-friendly) and `--only` to target
specific endpoints.

## Related docs

- Caching policy: `docs/performance/caching.md`
- Ingestion efficiency: `docs/performance/ingestion_efficiency.md`
- Queue scaling runbook: `docs/performance/queue_scaling.md`
- Load and soak tests: `docs/performance/load_tests.md`
