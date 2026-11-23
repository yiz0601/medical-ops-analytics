"""接口文档、响应模型与覆盖率配置校验（阶段四 · 步骤 3-5）。

    check_openapi()       拉取 /api/openapi.json，断言全部已注册路由都被文档覆盖
    check_response_model() 校验关键接口声明了 response_model 且统一外壳、含错误响应示例
    parse_coverage()      解析覆盖率输出并给出口径摘要
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from app.core.config import get_settings

# 必须出现在 OpenAPI 文档中的业务路由
EXPECTED_PATHS = [
    "/api/auth/login",
    "/api/auth/users",
    "/api/auth/profile",
    "/api/dashboard/overview",
    "/api/outpatient/metrics",
    "/api/inpatient/metrics",
    "/api/revenue/metrics",
    "/api/disease/metrics",
    "/api/resource/metrics",
    "/api/task/status",
    "/api/task/trigger",
    "/api/quality/report",
]

# 允许不声明统一外壳的场景：系统端点与文件流下载
EXEMPT_PATHS = {"/health", "/api/ping", "/api/dashboard/export"}
# 允许无 401 声明的公开端点
PUBLIC_PATHS = {"/api/auth/login"}


def _openapi(client) -> dict:
    settings = get_settings()
    response = client.get(f"{settings.api_prefix}/openapi.json")
    assert response.status_code == 200, response.text
    return response.json()


def check_openapi(client) -> dict:
    """校验 OpenAPI 文档：路由齐全、每个操作都有 tags 与 summary。"""
    spec = _openapi(client)
    assert spec["openapi"].startswith("3."), "OpenAPI 版本应为 3.x"
    assert spec["info"]["title"] and spec["info"]["version"]

    missing = [path for path in EXPECTED_PATHS if path not in spec["paths"]]
    assert not missing, f"以下路由未出现在 OpenAPI 文档中：{missing}"

    undocumented: list[str] = []
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            if not operation.get("tags") or not operation.get("summary"):
                undocumented.append(f"{method.upper()} {path}")
    assert not undocumented, f"缺少 tags/summary 的接口：{undocumented}"
    return spec


def check_response_model(client) -> None:
    """校验响应模型：业务接口返回统一外壳（ApiResponse[...]），受保护接口声明 401。"""
    spec = _openapi(client)
    problems: list[str] = []
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            responses = operation.get("responses", {})
            success = responses.get("200") or responses.get("201")
            if success is None:
                problems.append(f"{method.upper()} {path} 未声明成功响应")
                continue
            if path in EXEMPT_PATHS:
                continue
            rendered = json.dumps(success, ensure_ascii=False)
            if "ApiResponse" not in rendered:
                problems.append(f"{method.upper()} {path} 未使用统一响应模型 ApiResponse")
            if path not in PUBLIC_PATHS and "401" not in responses:
                problems.append(f"{method.upper()} {path} 未声明 401 错误响应")
    assert not problems, "响应模型声明问题：" + "; ".join(problems)


def parse_coverage() -> dict:
    """解析覆盖率输出（需以 pytest --cov=app 运行才会生成 .coverage）。"""
    result: dict[str, object] = {"measured": False, "total_percent": None, "summary": ""}
    coverage_file = Path(".coverage")
    if not coverage_file.exists():
        result["summary"] = "未生成 .coverage 文件：请使用 pytest --cov=app 运行"
        return result
    try:
        from coverage import Coverage
    except ImportError:  # pragma: no cover - 覆盖率插件缺失时降级
        result["summary"] = "未安装 coverage 插件"
        return result

    cov = Coverage(data_file=str(coverage_file))
    cov.load()
    buffer = StringIO()
    percent = cov.report(file=buffer, show_missing=False)
    result.update(
        {
            "measured": True,
            "total_percent": round(float(percent), 2),
            "summary": buffer.getvalue().strip()[:600],
        }
    )
    return result


# ---------------------------------------------------------------- 测试用例
def test_check_openapi(client):
    """全部业务路由均出现在 OpenAPI 文档中，且操作具备 tags 与 summary。"""
    spec = check_openapi(client)
    assert len(spec["paths"]) >= len(EXPECTED_PATHS)
    assert spec["info"]["description"].strip()


def test_check_response_model(client):
    """业务接口统一使用 ApiResponse 外壳，受保护接口声明 401。"""
    check_response_model(client)


def test_coverage_gate_configured():
    """pytest 配置中启用了覆盖率统计与 80% 门槛。"""
    config = Path("pytest.ini").read_text(encoding="utf-8")
    assert "--cov=app" in config
    assert "--cov-fail-under=80" in config


def test_parse_coverage():
    """覆盖率解析可给出总覆盖率与摘要（未生成数据时给出提示）。"""
    info = parse_coverage()
    assert "total_percent" in info
    if info["measured"]:
        assert float(info["total_percent"]) >= 0.0
        assert info["summary"]
