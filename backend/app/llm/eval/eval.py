"""NL2SQL 评测（阶段六 · 步骤 5）。

    load_evalset()                  读取 50 条标注数据
    evaluate(threshold=0.85)        执行评测并返回准确率与明细

评分口径：指标编码 + 维度值 + 粒度 三项全部命中才计为通过；
默认离线运行（规则引擎），配置模型后可对比模型解析效果。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.llm.nl2sql import map_metric_dim, parse_intent

EVALSET_PATH = Path(__file__).resolve().parent / "evalset.json"
DEFAULT_THRESHOLD = 0.85


def load_evalset(path: Path | str | None = None) -> dict[str, Any]:
    """读取评测集（含 meta 与 items）。"""
    target = Path(path) if path else EVALSET_PATH
    if not target.exists():
        raise FileNotFoundError(f"评测集不存在：{target}（可执行 python -m app.llm.eval.build_evalset 生成）")
    return json.loads(target.read_text(encoding="utf-8"))


def evaluate(threshold: float = DEFAULT_THRESHOLD, *, verbose: bool = False) -> dict[str, Any]:
    """执行评测，返回 {accuracy, passed, total, reached, by_topic, by_difficulty, details}。"""
    dataset = load_evalset()
    items: list[dict[str, Any]] = dataset.get("items", [])
    details: list[dict[str, Any]] = []
    by_topic: dict[str, dict[str, int]] = {}
    by_difficulty: dict[str, dict[str, int]] = {}

    for item in items:
        expect = item.get("expect_points", {})
        topic = str(item.get("topic", ""))
        difficulty = str(item.get("difficulty", ""))
        by_topic.setdefault(topic, {"total": 0, "passed": 0})
        by_difficulty.setdefault(difficulty, {"total": 0, "passed": 0})
        by_topic[topic]["total"] += 1
        by_difficulty[difficulty]["total"] += 1

        actual: dict[str, Any] = {"metric_code": None, "dim_value": None, "granularity": None}
        error = ""
        try:
            intent = map_metric_dim(parse_intent(item["question"]))
            actual = {
                "metric_code": intent.metric_code,
                "dim_value": intent.dim_value,
                "granularity": intent.granularity,
            }
        except Exception as exc:  # noqa: BLE001 - 解析失败计入不通过
            error = f"{type(exc).__name__}: {exc}"

        matched = (
            actual["metric_code"] == expect.get("metric_code")
            and actual["dim_value"] == expect.get("dim_value")
            and actual["granularity"] == expect.get("granularity")
        )
        if matched:
            by_topic[topic]["passed"] += 1
            by_difficulty[difficulty]["passed"] += 1

        details.append(
            {
                "id": item.get("id"),
                "question": item.get("question"),
                "topic": topic,
                "difficulty": difficulty,
                "expected": expect,
                "actual": actual,
                "passed": matched,
                "error": error,
            }
        )
        if verbose and not matched:
            print(f"[MISS] {item.get('id')} {item.get('question')} 期望 {expect} 实际 {actual}")

    total = len(details)
    passed = sum(1 for item in details if item["passed"])
    accuracy = round(passed / total, 4) if total else 0.0
    return {
        "metric": "NL2SQL 意图解析准确率",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": accuracy,
        "threshold": threshold,
        "reached": accuracy >= threshold,
        "by_topic": {
            topic: {**stat, "accuracy": round(stat["passed"] / stat["total"], 4) if stat["total"] else 0.0}
            for topic, stat in by_topic.items()
        },
        "by_difficulty": {
            level: {**stat, "accuracy": round(stat["passed"] / stat["total"], 4) if stat["total"] else 0.0}
            for level, stat in by_difficulty.items()
        },
        "details": details,
        "evalset": {"version": dataset.get("meta", {}).get("version"), "total": dataset.get("meta", {}).get("total")},
    }


if __name__ == "__main__":
    report = evaluate(verbose=True)
    print(
        f"\n评测结果：{report['passed']}/{report['total']} 命中率 {report['accuracy'] * 100:.2f}% "
        f"（阈值 {report['threshold'] * 100:.0f}%，{'达标' if report['reached'] else '未达标'}）"
    )
    for topic, stat in report["by_topic"].items():
        print(f"  {topic:<8} {stat['passed']}/{stat['total']} = {stat['accuracy'] * 100:.1f}%")
