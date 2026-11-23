"""公共维表初始化数据（阶段三 · 步骤 1）。

单一数据来源：`sql/dim/dim_tables.sql` 中的初始化数据与本文件保持一致，
`etl.jobs.init_dim` 用它装载维表（MySQL 与 SQLite 通用），测试断言其行数。

维表清单（4 张核心 + 2 张扩展）：
    dim_department  科室维表（标准码、名称、层级、院区、开放床位、人员数）
    dim_date        日期维表（年/季/月/周/星期/周末/节假日，覆盖数据期前后各 1 年）
    dim_disease     病种维表（ICD 编码、病种分类、DRG/DIP 分组、权重 RW）
    dim_fee_type    收费类别维表（挂号/检查/治疗/药品/耗材/床位等 + 收入归类）
    dim_drg_group   DRG 分组维表（病种 → 组别 → 权重，扩展表）
    dim_visit_type  号别字典（普通/专家/急诊/门诊/住院，扩展表）
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

# ---------------------------------------------------------------- 科室层级
# (dept_code, dept_name, parent_code, dept_level, dept_type, org_area, bed_cnt, doctor_cnt, nurse_cnt)
DEPARTMENT_ROWS: list[tuple[str, str, str | None, int, str, str, int, int, int]] = [
    # 一级：科室系（层级维度）
    ("NK", "内科系", None, 1, "科室系", "本部", 0, 0, 0),
    ("WK", "外科系", None, 1, "科室系", "本部", 0, 0, 0),
    ("MZ", "门急诊系", None, 1, "科室系", "本部", 0, 0, 0),
    ("QT", "其他科室", None, 1, "科室系", "本部", 0, 0, 0),
    # 二级：临床科室（与数据集 dept_code 一致，合计开放床位 177）
    ("HN", "呼吸内科", "NK", 2, "临床科室", "本部", 18, 12, 20),
    ("HX", "消化内科", "NK", 2, "临床科室", "本部", 17, 11, 19),
    ("SJ", "神经内科", "NK", 2, "临床科室", "本部", 18, 12, 20),
    ("XH", "心血管内科", "NK", 2, "临床科室", "本部", 18, 13, 21),
    ("GK", "骨科", "WK", 2, "临床科室", "本部", 18, 12, 20),
    ("PW", "普外科", "WK", 2, "临床科室", "本部", 18, 12, 20),
    ("FC", "妇产科", "WK", 2, "临床科室", "本部", 16, 11, 22),
    ("JZ", "急诊科", "MZ", 2, "临床科室", "本部", 18, 14, 24),
    ("EK", "儿科", "MZ", 2, "临床科室", "本部", 18, 12, 21),
    ("ICU", "重症医学科", "QT", 2, "临床科室", "本部", 18, 14, 30),
]

# ---------------------------------------------------------------- 病种与 DRG/DIP 分组
# (disease_code, disease_name, disease_category, drg_code, drg_name, rw, dip_group)
DISEASE_ROWS: list[tuple[str, str, str, str, str, float, str]] = [
    ("I10", "原发性高血压", "循环系统疾病", "FM19", "高血压", 0.62, "DIP-I10"),
    ("I25", "慢性缺血性心脏病", "循环系统疾病", "FM29", "慢性缺血性心脏病", 0.95, "DIP-I25"),
    ("I63", "脑梗死", "神经系统疾病", "BR29", "脑梗死", 1.35, "DIP-I63"),
    ("J18", "肺炎", "呼吸系统疾病", "ES35", "肺炎", 0.88, "DIP-J18"),
    ("J44", "慢阻肺", "呼吸系统疾病", "EX13", "慢性阻塞性肺疾病", 1.02, "DIP-J44"),
    ("A09", "感染性腹泻", "消化系统疾病", "GK13", "感染性腹泻", 0.55, "DIP-A09"),
    ("K35", "急性阑尾炎", "消化系统疾病", "GD19", "急性阑尾炎", 0.78, "DIP-K35"),
    ("C16", "胃癌", "肿瘤", "GR19", "胃恶性肿瘤", 2.85, "DIP-C16"),
    ("E11", "糖尿病", "内分泌与代谢疾病", "KS19", "2 型糖尿病", 0.72, "DIP-E11"),
    ("N18", "慢性肾脏病", "泌尿系统疾病", "LS35", "慢性肾脏病", 1.18, "DIP-N18"),
]

DRG_ROWS: list[tuple[str, str, str, float]] = [(d[0], d[3], d[4], d[5]) for d in DISEASE_ROWS]

# ---------------------------------------------------------------- 收费类别
# (fee_type_code, fee_type_name, fee_class, is_drug, is_consumable, sort_no)
FEE_TYPE_ROWS: list[tuple[str, str, str, int, int, int]] = [
    ("GH", "挂号费", "医疗服务性收入", 0, 0, 1),
    ("JC", "检查费", "检查检验收入", 0, 0, 2),
    ("JY", "检验费", "检查检验收入", 0, 0, 3),
    ("ZL", "治疗费", "医疗服务性收入", 0, 0, 4),
    ("SS", "手术费", "医疗服务性收入", 0, 0, 5),
    ("CW", "床位费", "医疗服务性收入", 0, 0, 6),
    ("HL", "护理费", "医疗服务性收入", 0, 0, 7),
    ("XY", "西药费", "药品收入", 1, 0, 8),
    ("ZC", "中成药费", "药品收入", 1, 0, 9),
    ("CL", "材料费", "耗材收入", 0, 1, 10),
]

# ---------------------------------------------------------------- 号别字典
# (visit_type_code, visit_type_name, visit_category)
VISIT_TYPE_ROWS: list[tuple[str, str, str]] = [
    ("PT", "普通", "门诊"),
    ("ZJ", "专家", "门诊"),
    ("JZ", "急诊", "门急诊"),
    ("OPD", "门诊", "门急诊"),
    ("IPD", "住院", "住院"),
]

# ---------------------------------------------------------------- 日期维表
# 数据统计期 2025-04-01 ~ 2025-06-30，日期维覆盖其前后各 1 年
DATE_START = "2024-04-01"
DATE_END = "2026-06-30"

# 法定节假日（示例口径：覆盖日期维范围内的主要节假日，用于节假日标记）
HOLIDAYS: dict[str, str] = {
    "2024-04-04": "清明节",
    "2024-04-05": "清明节",
    "2024-04-06": "清明节",
    "2024-05-01": "劳动节",
    "2024-05-02": "劳动节",
    "2024-05-03": "劳动节",
    "2024-05-04": "劳动节",
    "2024-05-05": "劳动节",
    "2024-06-10": "端午节",
    "2024-09-15": "中秋节",
    "2024-09-16": "中秋节",
    "2024-09-17": "中秋节",
    "2024-10-01": "国庆节",
    "2024-10-02": "国庆节",
    "2024-10-03": "国庆节",
    "2024-10-04": "国庆节",
    "2024-10-05": "国庆节",
    "2024-10-06": "国庆节",
    "2024-10-07": "国庆节",
    "2025-01-01": "元旦",
    "2025-01-28": "春节",
    "2025-01-29": "春节",
    "2025-01-30": "春节",
    "2025-01-31": "春节",
    "2025-02-01": "春节",
    "2025-02-02": "春节",
    "2025-02-03": "春节",
    "2025-02-04": "春节",
    "2025-04-04": "清明节",
    "2025-04-05": "清明节",
    "2025-04-06": "清明节",
    "2025-05-01": "劳动节",
    "2025-05-02": "劳动节",
    "2025-05-03": "劳动节",
    "2025-05-04": "劳动节",
    "2025-05-05": "劳动节",
    "2025-05-31": "端午节",
    "2025-06-01": "端午节",
    "2025-06-02": "端午节",
    "2025-10-01": "国庆节",
    "2025-10-02": "国庆节",
    "2025-10-03": "国庆节",
    "2025-10-04": "国庆节",
    "2025-10-05": "国庆节",
    "2025-10-06": "国庆节",
    "2025-10-07": "国庆节",
    "2025-10-08": "国庆节",
    "2026-01-01": "元旦",
    "2026-02-16": "春节",
    "2026-02-17": "春节",
    "2026-02-18": "春节",
    "2026-02-19": "春节",
    "2026-02-20": "春节",
    "2026-02-21": "春节",
    "2026-02-22": "春节",
    "2026-04-04": "清明节",
    "2026-04-05": "清明节",
    "2026-04-06": "清明节",
    "2026-05-01": "劳动节",
    "2026-05-02": "劳动节",
    "2026-05-03": "劳动节",
    "2026-05-04": "劳动节",
    "2026-05-05": "劳动节",
    "2026-06-19": "端午节",
    "2026-06-20": "端午节",
    "2026-06-21": "端午节",
}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
STAT_PERIOD_RANGE = ("2025-04-01", "2025-06-30")


def build_date_rows(start: str = DATE_START, end: str = DATE_END) -> list[dict[str, Any]]:
    """生成日期维表行：日期键、年月周日、周末与节假日标记。"""
    begin = _dt.date.fromisoformat(start)
    finish = _dt.date.fromisoformat(end)
    stat_begin = _dt.date.fromisoformat(STAT_PERIOD_RANGE[0])
    stat_finish = _dt.date.fromisoformat(STAT_PERIOD_RANGE[1])
    rows: list[dict[str, Any]] = []
    day = begin
    while day <= finish:
        iso_year, iso_week, _ = day.isocalendar()
        key = day.strftime("%Y%m%d")
        rows.append(
            {
                "date_key": int(key),
                "date_value": day,
                "year": day.year,
                "quarter": (day.month - 1) // 3 + 1,
                "month": day.month,
                "year_month": day.strftime("%Y-%m"),
                "day_of_month": day.day,
                "week_of_year": iso_week,
                "iso_year": iso_year,
                "day_of_week": day.isoweekday(),
                "weekday_name": WEEKDAY_CN[day.isoweekday() - 1],
                "is_weekend": 1 if day.isoweekday() >= 6 else 0,
                "is_holiday": 1 if key in {h.replace("-", "") for h in HOLIDAYS} else 0,
                "holiday_name": HOLIDAYS.get(day.isoformat(), ""),
                "in_stat_period": 1 if stat_begin <= day <= stat_finish else 0,
            }
        )
        day += _dt.timedelta(days=1)
    return rows


# 各维表期望行数（测试与运维核对基线）
DIM_EXPECTED_ROWS: dict[str, int] = {
    "dim_department": len(DEPARTMENT_ROWS),   # 14（4 科室系 + 10 临床科室）
    "dim_disease": len(DISEASE_ROWS),         # 10
    "dim_fee_type": len(FEE_TYPE_ROWS),       # 10
    "dim_drg_group": len(DRG_ROWS),           # 10
    "dim_visit_type": len(VISIT_TYPE_ROWS),   # 5
    "dim_date": len(build_date_rows()),       # 821（数据期前后各 1 年）
}
