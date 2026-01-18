"""
Middleware for request-scoped tenancy concerns.
"""

import logging
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Attaches a request_id to request.state for correlation and adds it to responses.
    """

    async def dispatch(self, request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        logger.debug("request.start", extra={"request_id": request_id, "path": request.url.path})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
