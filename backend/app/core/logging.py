# This middleware records a structured JSON log for each request.
# It captures latency, route, tenant, user, and request_id for traceability.

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.perf import finish_request, record_request_perf, start_request


_STANDARD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}

_ALWAYS_FIELDS = {
    "request_id",
    "tenant_id",
    "user_id",
    "route",
    "method",
    "status_code",
    "duration_ms",
    "error_code",
    "trace_id",
    "span_id",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS:
                continue
            if value is None and key not in _ALWAYS_FIELDS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def get_structured_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


logger = get_structured_logger("api_logger")


def _resolve_route(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path or request.url.path


def _resolve_user_id(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split()[1]
        try:
            payload = decode_access_token(token)
            return payload.get("user_id") or payload.get("sub")
        except Exception:
            return None
    return None


class APILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = monotonic()
        handler_start = monotonic()
        perf_stats = None
        if settings.PERF_PROFILING:
            perf_stats = start_request(
                route=request.url.path,
                method=request.method,
                request_id=getattr(request.state, "request_id", None),
                tenant_id=getattr(request.state, "tenant_id", None),
            )
        from app.core.tracing import get_trace_id, get_span_id
        try:
            response = await call_next(request)
        except Exception:
            handler_time_ms = round((monotonic() - handler_start) * 1000.0, 2)
            duration_ms = round((monotonic() - start) * 1000.0, 2)
            if settings.PERF_PROFILING:
                perf_stats = finish_request(handler_time_ms=handler_time_ms)
            db_time_ms = round(perf_stats.db_time_ms, 2) if perf_stats else 0.0
            db_queries_count = perf_stats.db_queries_count if perf_stats else 0
            extra = {
                "request_id": getattr(request.state, "request_id", None),
                "tenant_id": getattr(request.state, "tenant_id", None),
                "user_id": _resolve_user_id(request),
                "route": _resolve_route(request),
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
                "duration_ms": duration_ms,
                "error_code": "unhandled_exception",
                "trace_id": get_trace_id(),
                "span_id": get_span_id(),
            }
            if settings.PERF_PROFILING and perf_stats:
                extra.update(
                    {
                        "db_time_ms": db_time_ms,
                        "db_queries_count": db_queries_count,
                        "handler_time_ms": perf_stats.handler_time_ms,
                        "serialize_time_ms": perf_stats.serialize_time_ms,
                        "slow_queries": perf_stats.slow_queries or None,
                        "slow_queries_dropped": perf_stats.slow_queries_dropped or None,
                    }
                )
            logger.exception("request.failed", extra=extra)
            record_request_perf(
                request_id=getattr(request.state, "request_id", None),
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                db_time_ms=db_time_ms,
                db_queries_count=db_queries_count,
            )
            raise

        handler_time_ms = round((monotonic() - handler_start) * 1000.0, 2)
        duration_ms = round((monotonic() - start) * 1000.0, 2)
        if settings.PERF_PROFILING:
            perf_stats = finish_request(handler_time_ms=handler_time_ms)
        db_time_ms = round(perf_stats.db_time_ms, 2) if perf_stats else 0.0
        db_queries_count = perf_stats.db_queries_count if perf_stats else 0
        extra = {
            "request_id": getattr(request.state, "request_id", None),
            "tenant_id": getattr(request.state, "tenant_id", None),
            "user_id": _resolve_user_id(request),
            "route": _resolve_route(request),
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "error_code": response.headers.get("X-Error-Code"),
            "trace_id": get_trace_id(),
            "span_id": get_span_id(),
        }
        if settings.PERF_PROFILING and perf_stats:
            extra.update(
                {
                    "db_time_ms": db_time_ms,
                    "db_queries_count": db_queries_count,
                    "handler_time_ms": perf_stats.handler_time_ms,
                    "serialize_time_ms": perf_stats.serialize_time_ms,
                    "slow_queries": perf_stats.slow_queries or None,
                    "slow_queries_dropped": perf_stats.slow_queries_dropped or None,
                }
            )
        logger.info("request.completed", extra=extra)
        record_request_perf(
            request_id=getattr(request.state, "request_id", None),
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            db_time_ms=db_time_ms,
            db_queries_count=db_queries_count,
        )
        return response
