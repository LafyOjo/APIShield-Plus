# Ingestion Efficiency and Cost Controls

Primary implementation files:

- Browser ingest: `backend/app/api/ingest.py`
- Security ingest: `backend/app/api/ingest_security.py`
- Sampling engine: `backend/app/core/sampling.py`
- Usage metering: `backend/app/core/usage.py`
- Agent batching/compression: `agent/src/agent.js`

## Client-side controls

The browser agent supports:

- batching by count and interval
- gzip compression (`Content-Encoding: gzip`)
- retry with exponential backoff and jitter

## Server-side batching

Browser ingest uses batch code paths:

- bulk behavior event insert (`create_behaviour_events_bulk`)
- bulk session upsert (`upsert_behaviour_sessions_bulk`)

This avoids per-event roundtrips under load.

## Sampling policy

Rules can target:

- event type
- path prefix/pattern
- priority

High-value signals are always kept:

- login events
- checkout funnel events
- JavaScript error events
- form submit/failure events

Low-value traffic can be sampled down.

## Quota and graceful degradation

Per-tenant limits are resolved from entitlements.

When near or over quota:

- high-priority events are preserved
- low-priority events can be dropped
- quota overrun returns `429` for low-priority-only payloads

## Usage accounting

Per tenant usage tracks:

- events ingested
- raw events stored
- aggregate rows stored
- events sampled out
- estimated storage bytes

## Retention economics

- raw data retention is shorter
- aggregate retention is longer
- legal hold and plan limits still apply via retention policies

## Backpressure observability

Track in logs and metrics:

- dropped events
- sampled-out counts
- quota rejections (`429`)
- ingest latency and error rates

Use `docs/performance/load_tests.md` and `docs/performance/chaos_drills.md` for stress validation.
