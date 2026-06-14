# 职责：提供 HTTP 请求追踪、结构化日志基础配置和稳定 API 错误响应。
# 不做什么：不承载业务异常分类，不接入外部 APM，不读取或修改业务数据。
# 允许依赖层：标准库、FastAPI/Starlette、app.config。
# 谁不应该 import：app.models、app.config、业务算法脚本不应 import 本横切入口。
"""Minimal observability helpers for FastAPI entrypoints."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.config import get_settings

REQUEST_ID_HEADER = "X-Request-ID"
MIN_REQUEST_ID_LENGTH = 8
MAX_REQUEST_ID_LENGTH = 128
_current_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _current_id.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if get_settings().DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    )
    logging.getLogger().addFilter(RequestIdFilter())


def _new_request_id(incoming: str | None) -> str:
    if incoming and MIN_REQUEST_ID_LENGTH <= len(incoming) <= MAX_REQUEST_ID_LENGTH:
        return incoming
    return uuid.uuid4().hex


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    try:
        incoming_request_id = request.headers[REQUEST_ID_HEADER]
    except KeyError:
        incoming_request_id = None
    request_id = _new_request_id(incoming_request_id)
    token = _current_id.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logging.getLogger("app.request").info(
            "method=%s path=%s elapsed_ms=%s",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        _current_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def error_payload(
    error_code: str, message: str, status_code: int, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "status_code": status_code,
        "request_id": get_request_id(),
    }
    if extra:
        payload["extra"] = extra
    return payload


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload("http_error", detail, exc.status_code),
        headers={REQUEST_ID_HEADER: get_request_id()},
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "validation_error",
            "请求参数校验失败",
            422,
            extra={"errors": exc.errors()},
        ),
        headers={REQUEST_ID_HEADER: get_request_id()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("app.unhandled").exception(
        "method=%s path=%s unhandled_exception",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content=error_payload("internal_error", "服务内部错误", 500),
        headers={REQUEST_ID_HEADER: get_request_id()},
    )
