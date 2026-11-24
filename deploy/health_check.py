"""部署健康检查（阶段七 · 步骤 2）。

    check_service_health(service_name)  校验单个容器健康状态（docker inspect + HTTP 探针）
    check_all()                         校验四服务（mysql / backend / frontend / nginx）与 /api 反代链路
    main()                              命令行入口：python deploy/health_check.py

说明：
    * 容器状态通过 `docker inspect` 读取 Health.Status；
    * HTTP 探针按服务暴露方式执行：nginx → http://127.0.0.1/health，backend → 容器内 /health；
    * 未安装 Docker 时（本地开发）自动降级为 HTTP 探针模式，并提示跳过容器检查。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request

SERVICES = {
    "mysql": {"container": "moa-mysql", "http": None},
    "backend": {"container": "moa-backend", "http": "http://127.0.0.1:8000/health"},
    "frontend": {"container": "moa-frontend", "http": "http://127.0.0.1:4173/"},
    "nginx": {"container": "moa-nginx", "http": "http://127.0.0.1/health"},
}
API_PROBE = "http://127.0.0.1/api/ping"


def _docker_inspect(container: str) -> tuple[bool, str]:
    """读取容器运行状态与健康检查结果。"""
    try:
        output = subprocess.run(
            ["docker", "inspect", "--format", "{{json .State}}", container],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return False, f"docker 不可用：{type(exc).__name__}"
    if output.returncode != 0:
        return False, (output.stderr or "容器不存在").strip()[:120]
    try:
        state = json.loads(output.stdout)
    except json.JSONDecodeError:
        return False, "docker inspect 输出解析失败"
    health = (state.get("Health") or {}).get("Status", "none")
    running = bool(state.get("Running"))
    return running and health in {"healthy", "none"}, f"running={running} health={health}"


def _http_probe(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """HTTP 探针：2xx/3xx 视为通过。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"连接失败：{type(exc).__name__}"


def check_service_health(service_name: str, *, skip_docker: bool = False) -> dict:
    """校验单个服务健康状态，返回 {service, docker_ok, http_ok, healthy, detail}。"""
    if service_name not in SERVICES:
        raise KeyError(f"未知服务：{service_name}，可选 {list(SERVICES)}")
    config = SERVICES[service_name]

    docker_ok, docker_detail = (False, "已跳过容器检查")
    if not skip_docker:
        docker_ok, docker_detail = _docker_inspect(config["container"])

    http_ok, http_detail = (True, "无 HTTP 探针")
    if config["http"]:
        http_ok, http_detail = _http_probe(str(config["http"]))

    healthy = http_ok if skip_docker else (docker_ok and http_ok)
    return {
        "service": service_name,
        "container": config["container"],
        "docker_ok": docker_ok,
        "docker_detail": docker_detail,
        "http_ok": http_ok,
        "http_detail": http_detail,
        "healthy": healthy,
    }


def check_all(*, skip_docker: bool = False) -> dict:
    """校验四服务与 /api 反代链路。"""
    results = [check_service_health(name, skip_docker=skip_docker) for name in SERVICES]
    api_ok, api_detail = _http_probe(API_PROBE)
    return {
        "services": results,
        "api_proxy": {"url": API_PROBE, "ok": api_ok, "detail": api_detail},
        "all_healthy": all(item["healthy"] for item in results) and api_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="医疗运营平台部署健康检查")
    parser.add_argument("--service", help="仅检查指定服务：mysql/backend/frontend/nginx")
    parser.add_argument("--skip-docker", action="store_true", help="跳过容器状态检查（仅做 HTTP 探针）")
    args = parser.parse_args()

    if args.service:
        result = check_service_health(args.service, skip_docker=args.skip_docker)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["healthy"] else 1

    summary = check_all(skip_docker=args.skip_docker)
    print(f"{'服务':<10}{'容器':<14}{'容器状态':<22}{'HTTP 探针':<18}{'结论'}")
    for item in summary["services"]:
        print(
            f"{item['service']:<10}{item['container']:<14}{item['docker_detail'][:20]:<22}"
            f"{item['http_detail']:<18}{'✅ 健康' if item['healthy'] else '❌ 异常'}"
        )
    api = summary["api_proxy"]
    print(f"\n/api 反代链路：{api['url']} → {api['detail']} {'✅' if api['ok'] else '❌'}")
    print(f"\n总体结论：{'✅ 四服务与反代链路均健康' if summary['all_healthy'] else '❌ 存在异常服务'}")
    return 0 if summary["all_healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
