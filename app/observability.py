
from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger("aegisflow.access")

# Accept only simple, bounded request IDs from trusted clients.
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Add a request ID, timing, and structured access logs."""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        started_at = time.perf_counter()

        incoming_id = request.headers.get("X-Request-ID", "")
        if REQUEST_ID_PATTERN.fullmatch(incoming_id):
            request_id = incoming_id
        else:
            request_id = str(uuid4())

        request.state.request_id = request_id
        status_code = 500
        exception_type = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            # Avoid logging exception messages, which can contain sensitive
            # values. The exception class is useful for initial diagnosis.
            exception_type = type(exc).__name__
            raise

        finally:
            duration_ms = round(
                (time.perf_counter() - started_at) * 1000,
                2,
            )

            record = {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }

            if exception_type:
                record["exception_type"] = exception_type

            logger.info(
                json.dumps(record, separators=(",", ":"), ensure_ascii=False)
            )
