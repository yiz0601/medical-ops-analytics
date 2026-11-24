"""评测集生成脚本（一次性工具，产物为 evalset.json）。

50 条标注数据覆盖八大分析主题，expect_points 为人工标注的期望意图
（指标编码 / 维度值 / 粒度），不通过调用 parse_intent 反推，保证评测独立。

用法：python -m app.llm.eval.build_evalset
"""

from __future__ import annotations

import json
from pathlib import Path

# (question, metric_code, dim_value, granularity, topic, difficulty)
CASES: list[tuple[str, str, str | None, str, str, str]] = [
    # ---------------- 门诊主题（10）
    ("本月门诊人次是多少", "M01", "ALL", "month", "门诊", "easy"),
    ("上月门诊人次", "M01", "ALL", "month", "门诊", "easy"),
    ("本季度全院门诊人次是多少", "M01", "ALL", "period", "门诊", "easy"),
    ("6月呼吸科门诊人次", "M01", "HN", "month", "门诊", "medium"),
    ("门诊号别结构占比", "M02", "ALL", "period", "门诊", "easy"),
    ("儿科门诊次均费用", "M03", "EK", "period", "门诊", "medium"),
    ("上月全院门诊次均费用", "M03", "ALL", "month", "门诊", "medium"),
    ("门急诊人次本季度多少", "M06", "ALL", "period", "门诊", "easy"),
    ("上月门诊收入", "M07", "ALL", "month", "门诊", "easy"),
    ("各科室门诊人次排名", "M01", None, "period", "门诊", "medium"),
    # ---------------- 住院主题（11）
    ("本季度出院人次", "M08", "ALL", "period", "住院", "easy"),
    ("骨科出院人次上个月多少", "M08", "GK", "month", "住院", "hard"),
    ("入院人次", "M09", "ALL", "period", "住院", "easy"),
    ("实际占用总床日数", "M10", "ALL", "period", "住院", "medium"),
    ("上月呼吸科床位使用率趋势如何", "M11", "HN", "month", "住院", "hard"),
    ("各科室床位使用率排名", "M11", None, "period", "住院", "medium"),
    ("儿科平均住院日这几个月怎么变化的", "M12", "EK", "month", "住院", "hard"),
    ("全院平均住院日", "M12", "ALL", "period", "住院", "easy"),
    ("住院次均费用", "M13", "ALL", "period", "住院", "easy"),
    ("手术占比", "M14", "ALL", "period", "住院", "easy"),
    ("6月住院收入", "M15", "ALL", "month", "住院", "medium"),
    # ---------------- 收入主题（11）
    ("本季度医疗收入合计", "M16", "ALL", "period", "收入", "easy"),
    ("6月总收入", "M16", "ALL", "month", "收入", "easy"),
    ("各科室医疗收入排名", "M16", None, "period", "收入", "medium"),
    ("药品收入本季度", "M17", "ALL", "period", "药品", "easy"),
    ("上个月耗材收入", "M18", "ALL", "month", "耗材", "medium"),
    ("6月的药占比是多少", "M19", "ALL", "month", "药品", "medium"),
    ("各科室药占比对比", "M19", None, "period", "药品", "medium"),
    ("耗占比", "M20", "ALL", "period", "耗材", "easy"),
    ("检查检验收入占比", "M21", "ALL", "period", "收入", "easy"),
    ("医疗服务性收入占比", "M22", "ALL", "period", "收入", "easy"),
    ("收入增长率", "M33", "ALL", "period", "收入", "medium"),
    # ---------------- 病种主题（6）
    ("DRG 入组率", "M23", "ALL", "period", "病种", "easy"),
    ("CMI 病例组合指数", "M24", "ALL", "period", "病种", "medium"),
    ("各科室 CMI 对比", "M24", None, "period", "病种", "medium"),
    ("费用消耗指数", "M25", "ALL", "period", "病种", "medium"),
    ("时间消耗指数", "M26", "ALL", "period", "病种", "medium"),
    ("低风险组死亡率", "M27", "ALL", "period", "病种", "easy"),
    # ---------------- 资源效率主题（5）
    ("医师人均门诊人次", "M28", "ALL", "period", "资源效率", "easy"),
    ("床护比", "M29", "ALL", "period", "资源效率", "easy"),
    ("百元医疗收入耗材消耗", "M30", "ALL", "period", "耗材", "medium"),
    ("各科室床位使用率对比", "M11", None, "period", "资源效率", "medium"),
    ("ICU 床位使用率", "M11", "ICU", "period", "资源效率", "hard"),
    # ---------------- 患者服务主题（3）
    ("患者复诊率", "M31", "ALL", "period", "患者服务", "easy"),
    ("检验阳性率", "M32", "ALL", "period", "患者服务", "easy"),
    ("急诊科检验阳性率", "M32", "JZ", "period", "患者服务", "medium"),
    # ---------------- 跨主题 / 边界（4）
    ("本季度消化内科平均住院日是多少", "M12", "HX", "period", "住院", "medium"),
    ("普外科上个月手术占比", "M14", "PW", "month", "住院", "hard"),
    ("妇产科 6 月出院人次", "M08", "FC", "month", "住院", "hard"),
    ("6 月各科室医疗收入排名", "M16", None, "month", "收入", "hard"),
]

OUTPUT = Path(__file__).resolve().parent / "evalset.json"


def build() -> dict:
    items = [
        {
            "id": f"Q{index:03d}",
            "question": question,
            "topic": topic,
            "difficulty": difficulty,
            "expect_points": {
                "metric_code": metric,
                "dim_value": dim,
                "granularity": granularity,
            },
        }
        for index, (question, metric, dim, granularity, topic, difficulty) in enumerate(CASES, start=1)
    ]
    payload = {
        "meta": {
            "name": "医疗运营 NL2SQL 评测集",
            "version": "V1.0",
            "total": len(items),
            "topics": sorted({item["topic"] for item in items}),
            "granularities": ["day", "month", "period"],
            "scoring": "指标编码 + 维度值 + 粒度 三项全对才计为通过",
        },
        "items": items,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"已生成 {OUTPUT}：{result['meta']['total']} 条，覆盖 {len(result['meta']['topics'])} 个主题")
