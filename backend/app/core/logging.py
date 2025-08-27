# This middleware is all about visibility. It logs every HTTP
# request that passes through the app, along with its method,
# path, and optionally the Authorization header if present.
# ------------------------------------------------------------

import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Configure a logger named "api_logger". We set the logging
# level to INFO so that normal request flow is recorded.
# Developers can raise or lower this as needed.
logger = logging.getLogger("api_logger")
logging.basicConfig(level=logging.INFO)


# Middleware means this code runs before and after each request.
# Here we grab the HTTP method + path, and optionally include
# the Authorization header for debugging. Then we call the
# downstream handler and return its response.
class APILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization")
        if token:
            logger.info("%s %s Authorization=%s", request.method, request.url.path, token)
        else:
            logger.info("%s %s", request.method, request.url.path)
        response = await call_next(request)
        return response
