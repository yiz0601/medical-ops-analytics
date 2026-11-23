"""统一响应模型（阶段四 · 步骤 1-5）。

所有接口统一外层包裹：`{"code": 0, "msg": "success", "data": {...}}`。
`ApiResponse[T]` 为泛型包装，各接口在此之上定义具体 data 模型。
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应外壳。"""

    code: int = Field(default=0, description="业务码：0 成功，非 0 见错误码表")
    msg: str = Field(default="success", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")

    model_config = {
        "json_schema_extra": {
            "examples": [{"code": 0, "msg": "success", "data": {}}],
        }
    }


class ErrorResponse(BaseModel):
    """错误响应示例模型（用于 OpenAPI responses 声明）。"""

    code: int = Field(default=50001, description="业务错误码")
    msg: str = Field(default="服务内部异常", description="错误描述")
    data: None = Field(default=None, description="错误时无业务数据")
