# Observability Foundation

This document summarizes the logging, metrics, and tracing foundations plus dashboards and alerts.

## Structured logs

- JSON logs emitted for each request with:
  - `request_id`, `tenant_id`, `user_id`
  - `route`, `method`, `status_code`, `duration_ms`
  - `error_code` (when provided)
- Request IDs are returned via `X-Request-ID` and surfaced in the frontend API client logs.

## Metrics (Prometheus)

Key series:

- `requests_total{route,status_code}`
- `request_duration_ms_bucket{route}`
- `ingest_events_total{tenant_id,website_id,environment_id,event_type,ingest_type}`
- `ingest_latency_ms_bucket{ingest_type}`
- `notifications_sent_total{channel_type,trigger_type}`
- `notifications_failed_total{channel_type,trigger_type}`
- `job_run_total{job_name,status}`

## Tracing

Lightweight spans are emitted in JSON logs via `trace_span()`:

- ingest: browser/security/integrity flows
- map: summary/drilldown queries
- notifications: dispatch + send
- jobs: geo enrich/aggregate, interpretation, recovery

## Dashboards

Grafana JSON templates:

- `grafana/api-health.json`
- `grafana/ingestion-throughput.json`
- `grafana/geo-pipeline-health.json`
- `grafana/notification-reliability.json`

## Alerts

Prometheus rule pack:

- `infra/k8s/prometheus-rules.yaml`

Includes:

- API 5xx error-rate spike
- Ingest 429 spikes
- Geo job failures
- Notification delivery failures