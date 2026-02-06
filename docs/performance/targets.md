# Performance Targets

These targets define the baseline service expectations for APIShield+ in staging and production.

## API latency (p95)
- Common dashboard reads (`/api/v1/incidents`, `/api/v1/trust/snapshots`): **< 300ms**
- Ingest write (`/api/v1/ingest/browser`): **< 150ms**
- Map summary (`/api/v1/map/summary`): **< 500ms** (typical ranges under plan limits)

## Notes
- Targets are measured using the `scripts/perf/bench.py` runner.
- Perf instrumentation is enabled via `PERF_PROFILING=true`.
- Use `--report-dir` (or `--output` + `--markdown`) to persist JSON + Markdown reports.
