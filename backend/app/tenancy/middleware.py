"""
Middleware for request-scoped tenancy concerns.
"""

import logging
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.ip import extract_client_ip
from app.core.request_meta import build_request_meta
from app.core.tracing import set_trace_id
from app.tenancy.constants import TENANT_HEADER

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Attaches a request_id to request.state for correlation and adds it to responses.
    """

    async def dispatch(self, request, call_next):
        request_id = (
            getattr(request.state, "request_id", None)
            or request.headers.get("X-Request-ID")
            or request.headers.get("X-Request-Id")
            or str(uuid4())
        )
        request.state.request_id = request_id
        set_trace_id(request_id)

        header_name = settings.TENANT_HEADER_NAME or TENANT_HEADER
        tenant_id = request.headers.get(header_name)
        request.state.tenant_id = tenant_id

        client_ip = extract_client_ip(request)
        request.state.client_ip = client_ip
        request.state.user_agent = request.headers.get("User-Agent")
        request.state.request_meta = build_request_meta(
            request,
            request_id=request_id,
            client_ip=client_ip,
            tenant_id=tenant_id,
        )

        logger.debug(
            "request.start",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "client_ip": client_ip,
            },
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
