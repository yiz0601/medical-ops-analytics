"""认证与用户相关模型（阶段四 · 步骤 2.2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64, description="登录账号")
    password: str = Field(min_length=1, max_length=128, description="登录密码")


class UserOut(BaseModel):
    id: int | None = Field(default=None, description="用户 ID")
    username: str = Field(description="登录账号")
    real_name: str = Field(default="", description="姓名")
    role_code: str = Field(description="角色编码：ADMIN / ANALYST / DEPT_USER")
    dept_code: str | None = Field(default=None, description="所属科室（科室用户必填）")


class TokenOut(BaseModel):
    access_token: str = Field(description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(description="有效期（秒）")
    user: UserOut = Field(description="用户信息")


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="登录账号")
    password: str = Field(min_length=8, max_length=128, description="初始密码（入库前 bcrypt 哈希）")
    real_name: str = Field(default="", max_length=64, description="姓名")
    role_code: str = Field(default="ANALYST", description="角色：ADMIN / ANALYST / DEPT_USER（或 admin/analyst/department）")
    dept_code: str | None = Field(default=None, description="科室编码（角色为 DEPT_USER 时必填）")
