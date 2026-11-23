"""维度字典：科室、费别归类、病种与模拟 DRG 分组、检验结果判定、年龄段。

字典口径与《指标口径手册》第 7 章（公共维表与字典）保持一致，
生产环境应改为读取 dim_dept / dim_fee_type / dim_disease / dim_drg_group 维表。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 科室
# dept_code -> (dept_name, dept_type, bed_cnt, org_area)
DEPT_DICT: dict[str, tuple[str, str, int, str]] = {
    "EK": ("儿科", "临床科室", 18, "本部"),
    "FC": ("妇产科", "临床科室", 16, "本部"),
    "GK": ("骨科", "临床科室", 18, "本部"),
    "HN": ("呼吸内科", "临床科室", 18, "本部"),
    "HX": ("消化内科", "临床科室", 17, "本部"),
    "ICU": ("重症医学科", "临床科室", 18, "本部"),
    "JZ": ("急诊科", "临床科室", 18, "本部"),
    "PW": ("普外科", "临床科室", 18, "本部"),
    "SJ": ("神经内科", "临床科室", 18, "本部"),
    "XH": ("心血管内科", "临床科室", 18, "本部"),
}
DEPT_NAME: dict[str, str] = {k: v[0] for k, v in DEPT_DICT.items()}
TOTAL_BEDS = sum(v[2] for v in DEPT_DICT.values())  # 177

# ---------------------------------------------------------------- 费别
# fee_type_code -> (fee_type_name, fee_class)
FEE_TYPE_DICT: dict[str, tuple[str, str]] = {
    "XY": ("西药费", "药品收入"),
    "ZC": ("中成药费", "药品收入"),
    "JC": ("检查费", "检查检验收入"),
    "JY": ("检验费", "检查检验收入"),
    "ZL": ("治疗费", "医疗服务性收入"),
    "SS": ("手术费", "医疗服务性收入"),
    "CL": ("材料费", "耗材收入"),
    "CW": ("床位费", "医疗服务性收入"),
    "HL": ("护理费", "医疗服务性收入"),
}
FEE_CLASS: dict[str, str] = {k: v[1] for k, v in FEE_TYPE_DICT.items()}

# ---------------------------------------------------------------- 号别
# 源数据只出现中文号别，统一映射为标准编码
VISIT_TYPE_DICT: dict[str, str] = {
    "普通": "PT",
    "专家": "ZJ",
    "急诊": "JZ",
    "门诊": "OPD",
    "住院": "IPD",
}

# ---------------------------------------------------------------- 病种与模拟 DRG 分组
# ICD-10 -> (disease_name, drg_code, rw)
DISEASE_DICT: dict[str, tuple[str, str, float]] = {
    "I10": ("原发性高血压", "FM19", 0.62),
    "I25": ("慢性缺血性心脏病", "FM29", 0.95),
    "I63": ("脑梗死", "BR29", 1.35),
    "J18": ("肺炎", "ES35", 0.88),
    "J44": ("慢阻肺", "EX13", 1.02),
    "A09": ("感染性腹泻", "GK13", 0.55),
    "K35": ("急性阑尾炎", "GD19", 0.78),
    "C16": ("胃癌", "GR19", 2.85),
    "E11": ("糖尿病", "KS19", 0.72),
    "N18": ("慢性肾脏病", "LS35", 1.18),
}
DISEASE_NAME: dict[str, str] = {k: v[0] for k, v in DISEASE_DICT.items()}
DRG_CODE: dict[str, str] = {k: v[1] for k, v in DISEASE_DICT.items()}
DRG_RW: dict[str, float] = {k: v[2] for k, v in DISEASE_DICT.items()}

# ---------------------------------------------------------------- 检验结果判定
LIS_RESULT_FLAG: dict[str, str] = {
    "阴性": "正常",
    "未见异常": "正常",
    "正常": "正常",
    "在参考范围内": "正常",
    "阳性": "异常",
    "偏高": "异常",
    "偏低": "异常",
    "异常": "异常",
}

# ---------------------------------------------------------------- 年龄段
AGE_GROUP_EDGES: tuple[int, int, int] = (14, 34, 59)  # 0-14 / 15-34 / 35-59 / 60+


def age_group_of(age: int | None) -> str:
    """年龄段归类：儿童 / 青年 / 中年 / 老年。"""
    if age is None:
        return "未知"
    child, youth, middle = AGE_GROUP_EDGES
    if age <= child:
        return "儿童"
    if age <= youth:
        return "青年"
    if age <= middle:
        return "中年"
    return "老年"
