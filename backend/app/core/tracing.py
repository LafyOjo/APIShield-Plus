from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from uuid import uuid4

from app.core.logging import get_structured_logger


_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)

logger = get_structured_logger("trace")


def set_trace_id(value: str | None) -> None:
    if value:
        _trace_id.set(value)


def get_trace_id() -> str | None:
    return _trace_id.get()


def get_span_id() -> str | None:
    return _span_id.get()


def _new_span_id() -> str:
    return uuid4().hex[:16]


@contextmanager
def trace_span(name: str, **fields):
    span_id = _new_span_id()
    token = _span_id.set(span_id)
    start = monotonic()
    logger.info(
        "span.start",
        extra={
            "trace_id": get_trace_id(),
            "span_id": span_id,
            "span_name": name,
            **fields,
        },
    )
    try:
        yield span_id
    except Exception:
        duration_ms = round((monotonic() - start) * 1000.0, 2)
        logger.exception(
            "span.error",
            extra={
                "trace_id": get_trace_id(),
                "span_id": span_id,
                "span_name": name,
                "duration_ms": duration_ms,
                **fields,
            },
        )
        raise
    finally:
        duration_ms = round((monotonic() - start) * 1000.0, 2)
        logger.info(
            "span.end",
            extra={
                "trace_id": get_trace_id(),
                "span_id": span_id,
                "span_name": name,
                "duration_ms": duration_ms,
                **fields,
            },
        )
        _span_id.reset(token)
