from __future__ import annotations

import re
from contextvars import ContextVar
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic, sleep
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.config import settings
_perf_logger = None


@dataclass
class PerfStats:
    route: str | None
    method: str | None
    request_id: str | None
    tenant_id: str | None
    db_time_ms: float = 0.0
    db_queries_count: int = 0
    handler_time_ms: float = 0.0
    serialize_time_ms: float = 0.0
    slow_queries: list[dict[str, Any]] = field(default_factory=list)
    slow_queries_dropped: int = 0


_perf_ctx: ContextVar[PerfStats | None] = ContextVar("perf_ctx", default=None)
_request_perf_lock = Lock()
_request_perf_records: deque[dict[str, Any]] = deque(maxlen=200)


def start_request(
    *,
    route: str | None,
    method: str | None,
    request_id: str | None,
    tenant_id: str | None,
) -> PerfStats:
    stats = PerfStats(
        route=route,
        method=method,
        request_id=request_id,
        tenant_id=tenant_id,
    )
    _perf_ctx.set(stats)
    return stats


def finish_request(
    *,
    serialize_time_ms: float | None = None,
    handler_time_ms: float | None = None,
) -> PerfStats | None:
    stats = _perf_ctx.get()
    if stats is None:
        return None
    if serialize_time_ms is not None:
        stats.serialize_time_ms = serialize_time_ms
    if handler_time_ms is not None:
        stats.handler_time_ms = handler_time_ms
    stats.serialize_time_ms = round(stats.serialize_time_ms, 2)
    stats.handler_time_ms = round(stats.handler_time_ms, 2)
    stats.db_time_ms = round(stats.db_time_ms, 2)
    _perf_ctx.set(None)
    return stats


def get_stats() -> PerfStats | None:
    return _perf_ctx.get()


def record_serialize_time(duration_ms: float) -> None:
    stats = _perf_ctx.get()
    if stats is None:
        return
    stats.serialize_time_ms += duration_ms


def record_request_perf(
    *,
    request_id: str | None,
    path: str,
    status_code: int,
    duration_ms: float,
    db_time_ms: float,
    db_queries_count: int,
) -> None:
    record = {
        "request_id": request_id,
        "path": path,
        "status_code": int(status_code),
        "duration_ms": round(float(duration_ms), 2),
        "db_time_ms": round(float(db_time_ms), 2),
        "db_queries_count": int(db_queries_count),
    }
    with _request_perf_lock:
        _request_perf_records.append(record)


def get_recent_request_perf_records(limit: int = 200) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    with _request_perf_lock:
        items = list(_request_perf_records)[-safe_limit:]
    items.reverse()
    return items


def clear_recent_request_perf_records() -> None:
    with _request_perf_lock:
        _request_perf_records.clear()


_QUOTED_RE = re.compile(r"'(?:''|[^'])*'")
_NUMBER_RE = re.compile(r"\b\d+\b")


def _fingerprint(statement: str) -> str:
    sanitized = " ".join(statement.strip().split())
    sanitized = _QUOTED_RE.sub("?", sanitized)
    sanitized = _NUMBER_RE.sub("?", sanitized)
    return sanitized[:500]


def _get_perf_logger():
    global _perf_logger
    if _perf_logger is None:
        from app.core.logging import get_structured_logger

        _perf_logger = get_structured_logger("perf_logger")
    return _perf_logger


@event.listens_for(Engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if settings.CHAOS_DB_LATENCY_MS and settings.CHAOS_DB_LATENCY_MS > 0:
        sleep(settings.CHAOS_DB_LATENCY_MS / 1000.0)
    if not settings.PERF_PROFILING:
        return
    stats = _perf_ctx.get()
    if stats is None:
        return
    conn.info.setdefault("query_start_time", []).append(monotonic())


@event.listens_for(Engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if not settings.PERF_PROFILING:
        return
    stats = _perf_ctx.get()
    if stats is None:
        return
    start_times = conn.info.get("query_start_time")
    if not start_times:
        return
    duration_ms = (monotonic() - start_times.pop(-1)) * 1000.0
    stats.db_queries_count += 1
    stats.db_time_ms += duration_ms
    threshold = settings.PERF_SLOW_QUERY_MS
    if threshold is None:
        return
    should_log = duration_ms >= threshold if threshold > 0 else True
    if should_log:
        fingerprint = _fingerprint(statement)
        limit = settings.PERF_SLOW_QUERY_MAX_PER_REQUEST
        if limit is None:
            limit = 20
        limit = min(limit, 20)
        if limit is not None and len(stats.slow_queries) >= limit:
            stats.slow_queries_dropped += 1
            return
        from app.core.metrics import record_slow_query

        payload = {
            "duration_ms": round(duration_ms, 2),
            "query_fingerprint": fingerprint,
            "route": stats.route,
            "method": stats.method,
            "request_id": stats.request_id,
            "tenant_id": stats.tenant_id,
            "path": stats.route,
        }
        record_slow_query(stats.route, stats.method)
        stats.slow_queries.append(
            {
                "duration_ms": payload["duration_ms"],
                "query_fingerprint": payload["query_fingerprint"],
            }
        )
        _get_perf_logger().warning("db.slow_query", extra=payload)
