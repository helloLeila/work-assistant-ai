"""中间件与异常处理。"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import redact_sensitive_text

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录请求日志。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        started_at = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            redact_sensitive_text(str(request.url.path)),
            response.status_code,
            elapsed_ms,
        )
        return response


async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """统一异常响应。"""
    logger.exception("未处理异常：%s", exc)
    return JSONResponse(
        status_code=500,
        content={"message": "服务暂时不可用，请稍后重试。"},
    )
