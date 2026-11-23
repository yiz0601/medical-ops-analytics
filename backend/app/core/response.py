"""统一响应、包装中间件与全局异常处理（阶段四 · 步骤 1、3）。

- `ok()` / `envelope()`   生成统一响应体 `{code, msg, data}`
- `EnvelopeMiddleware`    兜底包装：任何返回 JSON 且未包裹的响应自动加外壳
- `register_exception_handlers()`  把 HTTPException / 参数校验错误 / 未捕获异常统一转成外壳响应
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.schemas.common import ApiResponse

# HTTP 状态码 -> 业务错误码
ERROR_CODE_MAP: dict[int, int] = {
    400: 40001,
    401: 40101,
    403: 40301,
    404: 40401,
    405: 40501,
    409: 40901,
    422: 40001,
    429: 42901,
    500: 50001,
    503: 50301,
}

# 业务码 -> 默认提示
ERROR_MESSAGES: dict[int, str] = {
    0: "success",
    40001: "参数校验失败",
    40101: "未登录或令牌失效",
    40301: "无权限访问该资源",
    40302: "数据越权：超出可见科室范围",
    40401: "资源不存在",
    40501: "请求方法不允许",
    40901: "资源冲突",
    42901: "请求过于频繁",
    50001: "服务内部异常",
    50301: "依赖服务不可用",
}


class BusinessError(Exception):
    """业务异常：由服务层抛出，全局处理器统一转成外壳响应。"""

    def __init__(self, code: int = 40001, msg: str | None = None, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        self.code = code
        self.msg = msg or ERROR_MESSAGES.get(code, "业务异常")
        self.status_code = status_code
        super().__init__(self.msg)


def ok(data: Any = None, msg: str = "success", code: int = 0) -> dict[str, Any]:
    """构造成功响应体。"""
    return {"code": code, "msg": msg, "data": data}


def error_response(code: int, msg: str | None = None, status_code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    """构造错误 JSON 响应。"""
    payload = ApiResponse[Any](code=code, msg=msg or ERROR_MESSAGES.get(code, "请求失败"), data=None)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


class EnvelopeMiddleware(BaseHTTPMiddleware):
    """响应外壳中间件：未包裹的 JSON 响应自动补 `{code, msg, data}`。"""

    # 文档与 OpenAPI 端点不包裹，避免破坏 Swagger UI
    EXCLUDE_SUFFIXES = ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        if request.url.path.endswith(self.EXCLUDE_SUFFIXES):
            return response
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response
        if response.status_code >= 400:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
        try:
            payload = json.loads(body or b"null")
        except json.JSONDecodeError:
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        if isinstance(payload, dict) and {"code", "msg", "data"} <= set(payload):
            wrapped = payload
        else:
            wrapped = {
                "code": 0,
                "msg": "success",
                "data": payload,
            }

        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return JSONResponse(
            status_code=response.status_code,
            content=wrapped,
            headers=headers,
            background=response.background,  # type: ignore[arg-type]
        )


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（统一外壳 + 错误码）。"""

    @app.exception_handler(BusinessError)
    async def _business_error(_: Request, exc: BusinessError) -> JSONResponse:
        return error_response(exc.code, exc.msg, exc.status_code)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = ERROR_CODE_MAP.get(exc.status_code, 40001)
        detail = exc.detail if isinstance(exc.detail, str) else ERROR_MESSAGES.get(code, "请求失败")
        return error_response(code, detail, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(item) for item in first.get("loc", []) if item != "body")
        detail = f"参数校验失败：{loc} {first.get('msg', '')}".strip()
        return error_response(40001, detail, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(Exception)
    async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
        return error_response(50001, f"服务内部异常：{type(exc).__name__}", status.HTTP_500_INTERNAL_SERVER_ERROR)
