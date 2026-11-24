"""接口压测脚本（阶段七 · 步骤 5）。

    collect_endpoints(token=None)                      构造驾驶舱、指标、多维、问数接口的压测请求集合
    run_bench(concurrency=50, duration=300, endpoints)  执行并发压测，返回 P50/P95/P99、QPS 与错误率
    print_summary(result)                              输出压测汇总表

用法（先启动后端）：
    python -m tests.perf.bench --base-url http://127.0.0.1:8000 --concurrency 20 --duration 60
    python -m tests.perf.bench --dry-run          # 只打印请求集合，不发起压测

说明：本地冒烟用较小并发与时长；正式验收按 concurrency=50、duration=300 执行并留存结果。
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEMO_ACCOUNT = {"username": "admin", "password": "Admin@123"}
PERIOD = "?start_date=2025-04-01&end_date=2025-06-30&granularity=month"


def _post_json(url: str, payload: dict, token: str | None = None, timeout: float = 30.0):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _get_json(url: str, token: str | None = None, timeout: float = 30.0):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def login(base_url: str = DEFAULT_BASE_URL) -> str:
    """登录获取压测令牌。"""
    status, body = _post_json(f"{base_url}/api/auth/login", DEMO_ACCOUNT)
    if status != 200 or body.get("code") != 0:
        raise RuntimeError(f"压测登录失败：{status} {body}")
    return body["data"]["access_token"]


def collect_endpoints(token: str | None = None, base_url: str = DEFAULT_BASE_URL) -> list[dict]:
    """构造压测请求集合（覆盖驾驶舱、指标、多维与分析接口）。"""
    endpoints = [
        {"name": "驾驶舱总览", "method": "GET", "url": f"{base_url}/api/dashboard/overview{PERIOD}"},
        {"name": "科室看板", "method": "GET", "url": f"{base_url}/api/dashboard/dept?dept=HN{PERIOD}&granularity=month"},
        {"name": "门诊指标", "method": "GET", "url": f"{base_url}/api/outpatient/metrics{PERIOD}"},
        {"name": "住院指标", "method": "GET", "url": f"{base_url}/api/inpatient/metrics{PERIOD}"},
        {"name": "收入指标", "method": "GET", "url": f"{base_url}/api/revenue/metrics{PERIOD}"},
        {"name": "病种指标", "method": "GET", "url": f"{base_url}/api/disease/metrics{PERIOD}"},
        {"name": "多维查询", "method": "GET", "url": f"{base_url}/api/inpatient/metrics?metrics=M08,M11&dims=EK,HN&granularity=month"},
        {"name": "任务状态", "method": "GET", "url": f"{base_url}/api/task/status"},
        {"name": "质量报告", "method": "GET", "url": f"{base_url}/api/quality/report"},
        {"name": "告警站内信", "method": "GET", "url": f"{base_url}/api/system/alerts?limit=5"},
        {"name": "智能问数", "method": "POST", "url": f"{base_url}/api/llm/query", "payload": {"question": "上月呼吸科床位使用率趋势如何"}},
    ]
    for item in endpoints:
        item["token"] = token
    return endpoints


def _worker(endpoints: list[dict], duration: float, stop_at: float, latencies: dict, errors: dict, lock: threading.Lock):
    while time.time() < stop_at:
        for endpoint in endpoints:
            started = time.perf_counter()
            try:
                if endpoint["method"] == "GET":
                    status, _body = _get_json(endpoint["url"], endpoint.get("token"))
                else:
                    status, _body = _post_json(endpoint["url"], endpoint.get("payload", {}), endpoint.get("token"))
                cost_ms = (time.perf_counter() - started) * 1000
                with lock:
                    latencies[endpoint["name"]].append(cost_ms)
                    if status >= 400:
                        errors[endpoint["name"]] += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                with lock:
                    errors[endpoint["name"]] += 1
                    latencies[endpoint["name"]].append((time.perf_counter() - started) * 1000)
                _ = exc


def run_bench(
    concurrency: int = 50,
    duration: int = 300,
    endpoints: list[dict] | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
) -> dict:
    """执行并发压测，返回汇总结果（P50/P95/P99、QPS、错误率）。"""
    items = endpoints or collect_endpoints(login(base_url), base_url)
    latencies: dict[str, list[float]] = {item["name"]: [] for item in items}
    errors: dict[str, int] = {item["name"]: 0 for item in items}
    lock = threading.Lock()

    stop_at = time.time() + duration
    threads = [
        threading.Thread(target=_worker, args=(items, duration, stop_at, latencies, errors, lock), daemon=True)
        for _ in range(max(1, concurrency))
    ]
    started = time.time()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = max(time.time() - started, 1e-6)

    summary = {"concurrency": concurrency, "duration_s": round(elapsed, 2), "endpoints": [], "overall": {}}
    all_latencies: list[float] = []
    total_requests = 0
    total_errors = 0
    for item in items:
        values = sorted(latencies[item["name"]])
        total_requests += len(values)
        total_errors += errors[item["name"]]
        all_latencies.extend(values)
        if not values:
            summary["endpoints"].append({"name": item["name"], "requests": 0})
            continue
        summary["endpoints"].append(
            {
                "name": item["name"],
                "requests": len(values),
                "p50_ms": round(statistics.median(values), 2),
                "p95_ms": round(values[max(0, int(len(values) * 0.95) - 1)], 2),
                "p99_ms": round(values[max(0, int(len(values) * 0.99) - 1)], 2),
                "errors": errors[item["name"]],
                "error_rate": round(errors[item["name"]] / len(values) * 100, 2),
            }
        )

    all_sorted = sorted(all_latencies)
    summary["overall"] = {
        "total_requests": total_requests,
        "total_errors": total_errors,
        "qps": round(total_requests / elapsed, 2),
        "error_rate": round(total_errors / total_requests * 100, 2) if total_requests else 0.0,
        "p50_ms": round(statistics.median(all_sorted), 2) if all_sorted else None,
        "p95_ms": round(all_sorted[max(0, int(len(all_sorted) * 0.95) - 1)], 2) if all_sorted else None,
        "p99_ms": round(all_sorted[max(0, int(len(all_sorted) * 0.99) - 1)], 2) if all_sorted else None,
    }
    return summary


def print_summary(result: dict) -> None:
    """打印压测汇总表。"""
    overall = result.get("overall", {})
    print("=" * 78)
    print(f"压测汇总：并发 {result.get('concurrency')} / 时长 {result.get('duration_s')}s / "
          f"请求 {overall.get('total_requests')} / QPS {overall.get('qps')} / "
          f"错误率 {overall.get('error_rate')}%")
    print(f"整体延迟：P50 {overall.get('p50_ms')}ms / P95 {overall.get('p95_ms')}ms / P99 {overall.get('p99_ms')}ms")
    print("-" * 78)
    print(f"{'接口':<16}{'请求数':>8}{'P50(ms)':>10}{'P95(ms)':>10}{'P99(ms)':>10}{'错误率%':>9}")
    for item in result.get("endpoints", []):
        print(
            f"{item['name']:<16}{item.get('requests', 0):>8}{item.get('p50_ms', '-'):>10}"
            f"{item.get('p95_ms', '-'):>10}{item.get('p99_ms', '-'):>10}{item.get('error_rate', '-'):>9}"
        )
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description="医疗运营平台接口压测")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true", help="只打印请求集合")
    args = parser.parse_args()

    if args.dry_run:
        for item in collect_endpoints(None, args.base_url):
            print(f"{item['method']:<4} {item['name']:<10} {item['url']}")
        return 0

    token = login(args.base_url)
    endpoints = collect_endpoints(token, args.base_url)
    result = run_bench(args.concurrency, args.duration, endpoints, base_url=args.base_url)
    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
