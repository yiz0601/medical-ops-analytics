"""运营看板截图采集脚本（阶段七 · 成果物「运营看板截图」）。

前置条件：
    1) 后端已启动（默认 http://127.0.0.1:8000）且已装载数据
    2) 前端已启动（默认 http://127.0.0.1:5173，开发模式自带 /api 代理）
    3) pip install playwright && python -m playwright install chromium

用法：
    python deploy/capture_screenshots.py --base-url http://127.0.0.1:5173
    python deploy/capture_screenshots.py --only dashboard,revenue --headful

输出：docs/screenshots/*.png（1920×1080）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PAGES: list[tuple[str, str, str, str]] = [
    # (编号, 文件名, 路由, 说明)
    ("S-01", "01_login.png", "/login", "登录页"),
    ("S-02", "02_dashboard.png", "/dashboard", "管理驾驶舱"),
    ("S-03", "03_outpatient.png", "/outpatient", "门诊分析"),
    ("S-04", "04_inpatient.png", "/inpatient", "住院分析"),
    ("S-05", "05_revenue.png", "/revenue", "收入分析"),
    ("S-06", "06_disease_drg.png", "/disease", "病种分析（DRG/DIP）"),
    ("S-07", "07_resource.png", "/resource", "资源效率分析"),
    ("S-08", "08_report_center.png", "/report", "多维报表中心"),
    ("S-09", "09_ai_chat.png", "/ai", "智能问数"),
    ("S-10", "10_admin_users.png", "/admin/users", "用户管理"),
    ("S-11", "11_admin_tasks.png", "/admin/tasks", "任务管理"),
    ("S-12", "12_dept_isolation.png", "/dashboard", "科室用户视角（数据隔离）"),
]

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def capture(base_url: str, only: set[str] | None = None, headful: bool = False, wait_ms: int = 2500) -> int:
    """逐页登录并截图，返回成功数量。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright：pip install playwright && python -m playwright install chromium")
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page = context.new_page()

        # 先用管理员登录，写入 localStorage 令牌（前端 store 从 localStorage 恢复）
        page.goto(f"{base_url}/login", wait_until="networkidle")
        page.fill('input[autocomplete="username"]', "admin")
        page.fill('input[autocomplete="current-password"]', "Admin@123")
        page.click('button[type="submit"]')
        page.wait_for_timeout(wait_ms)
        if "/login" in page.url:
            print("[ERROR] 登录失败，请确认后端与前端均已启动、账号密码正确")
            browser.close()
            return 0

        for code, filename, route, desc in PAGES:
            key = filename.split("_", 1)[1].replace(".png", "")
            if only and key not in only:
                continue
            try:
                if code == "S-12":
                    # 切换为科室用户，验证数据隔离与管理菜单隐藏
                    page.evaluate("() => localStorage.clear()")
                    page.goto(f"{base_url}/login", wait_until="networkidle")
                    page.fill('input[autocomplete="username"]', "dept_hn")
                    page.fill('input[autocomplete="current-password"]', "Dept@123")
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(wait_ms)
                    page.goto(f"{base_url}{route}", wait_until="networkidle")
                else:
                    page.goto(f"{base_url}{route}", wait_until="networkidle")
                page.wait_for_timeout(wait_ms)
                target = OUTPUT_DIR / filename
                page.screenshot(path=str(target), full_page=True)
                saved += 1
                print(f"[OK]   {code} {desc:<18} -> {target.name}")
            except Exception as exc:  # noqa: BLE001 - 单页失败不影响其余
                print(f"[FAIL] {code} {desc}: {type(exc).__name__}: {exc}")

        browser.close()

    print(f"\n完成：成功 {saved} 张，输出目录 {OUTPUT_DIR}")
    print("提示：核对 docs/screenshots/README.md 第 4 节的人工检查要点后，再更新《成果物清单》状态。")
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="运营看板截图采集")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--only", default="", help="仅采集指定页面，逗号分隔（如 dashboard,revenue）")
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口（调试用）")
    parser.add_argument("--wait-ms", type=int, default=2500, help="每页等待渲染毫秒数")
    args = parser.parse_args()

    only = {item.strip() for item in args.only.split(",") if item.strip()} or None
    saved = capture(args.base_url, only, args.headful, args.wait_ms)
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
