from __future__ import annotations

from time import monotonic
from typing import Any

from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.perf import record_serialize_time


class PerfJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        if not settings.PERF_PROFILING:
            return super().render(content)
        start = monotonic()
        body = super().render(content)
        record_serialize_time((monotonic() - start) * 1000.0)
        return body
