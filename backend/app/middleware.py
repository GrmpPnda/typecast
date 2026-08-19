"""Application middleware for request logging and error handling."""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("typecast.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and duration."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.startswith("/uploads"):
            return await call_next(request)

        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s %s %s - 500 (%.1fms) [unhandled exception]",
                request_id, method, path, duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        status = response.status_code

        if status >= 500:
            logger.error("%s %s %s - %d (%.1fms)", request_id, method, path, status, duration_ms)
        elif status >= 400:
            logger.warning("%s %s %s - %d (%.1fms)", request_id, method, path, status, duration_ms)
        else:
            logger.info("%s %s %s - %d (%.1fms)", request_id, method, path, status, duration_ms)

        return response
