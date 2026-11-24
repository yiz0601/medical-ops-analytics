"""指标口径知识问答（阶段六 · 步骤 2）。

    kb_answer(question)     手册分块检索 + 模型组织答案，返回 {answer, refs}
未命中手册片段时明确回答"手册中未收录"，不猜测；模型不可用时返回片段原文摘录。
"""

from __future__ import annotations

from typing import Any

from app.llm.client import get_client
from app.llm.prompts import build_kb_prompt

# 手册知识片段（对应《指标口径手册》章节，keywords 用于轻量检索）
KB_SNIPPETS: list[dict[str, Any]] = [
    {
        "title": "M01 门诊人次口径",
        "keywords": ["门诊人次", "门诊量", "M01"],
        "content": "M01 门诊人次 = COUNT(DISTINCT visit_id)，按 visit_date 归属统计期；来源 dwd_outpatient_visit_detail；"
                   "同一患者多次就诊分别计数，不剔除退号。基线（2025-04-01~06-30）：9,000 人次。",
        "ref": "《指标口径手册》4.1 / 台账 M01",
    },
    {
        "title": "M03 门诊次均费用口径",
        "keywords": ["门诊次均", "次均费用", "M03"],
        "content": "M03 门诊次均费用 = Σfee_amount ÷ 门诊人次，取登记口径字段（非流水口径）；"
                   "基线 425.15 元。流水口径合计与登记口径不可混用。",
        "ref": "《指标口径手册》4.1 / K1",
    },
    {
        "title": "M08 出院人次口径",
        "keywords": ["出院人次", "出院量", "M08"],
        "content": "M08 出院人次按 discharge_date 归属统计期，来源 dwd_inpatient_visit_detail；"
                   "基线 1,500 人次。注意 2025-06-30 集中出院 190 例（窗口截断效应）。",
        "ref": "《指标口径手册》4.2 / K6",
    },
    {
        "title": "M11 床位使用率口径",
        "keywords": ["床位使用率", "床位利用率", "M11"],
        "content": "M11 床位使用率 = 实际占用总床日数 ÷ (开放床位数 × 统计天数) × 100%；"
                   "开放床位取 dim_department.bed_cnt（合计 177 张）；基线 88.89%。当日出入院计 0 床日。",
        "ref": "《指标口径手册》4.2 / 7.1",
    },
    {
        "title": "M12 平均住院日口径",
        "keywords": ["平均住院日", "住院天数", "M12"],
        "content": "M12 平均住院日 = 实际占用总床日数 ÷ 出院人次；基线 9.54 天；含 17 例当日出入院（计 0 天）。",
        "ref": "《指标口径手册》4.2",
    },
    {
        "title": "M16 医疗收入合计口径",
        "keywords": ["医疗收入", "总收入", "收入合计", "M16"],
        "content": "M16 医疗收入合计 = 门诊收入 + 住院收入（流水口径，来源 dwd_charge_detail）；基线 44,260,283.80 元。"
                   "财务口径合计为 41,446,631.11 元，两者差异 -6.36%（见 K2）。",
        "ref": "《指标口径手册》4.3 / 2.2",
    },
    {
        "title": "M19/M20 药占比与耗占比口径",
        "keywords": ["药占比", "耗占比", "药品收入占比", "M19", "M20"],
        "content": "药占比 = 药品收入 ÷ 医疗收入 × 100%，耗占比 = 耗材收入 ÷ 医疗收入 × 100%；"
                   "默认取财务口径（30.00% / 10.00%），看板可切换流水口径（22.11% / 11.02%）。",
        "ref": "《指标口径手册》4.3 / K2",
    },
    {
        "title": "M23–M26 DRG 相关指标口径",
        "keywords": ["DRG", "入组率", "CMI", "消耗指数", "病种", "M23", "M24", "M25", "M26"],
        "content": "DRG 入组率 = 入组病例数 ÷ 出院人次；CMI = Σ(权重 × 例数) ÷ 入组病例数（基线 1.09）；"
                   "费用/时间消耗指数 = 实际值 ÷ (全院次均 × ΣRW)，基线均 0.9174。分组来源为 dim_disease 模拟分组，生产需替换院方分组器。",
        "ref": "《指标口径手册》4.4 / K3",
    },
    {
        "title": "M31 患者复诊率口径",
        "keywords": ["复诊率", "复诊", "M31"],
        "content": "M31 患者复诊率 = 复诊人次 ÷ 门诊人次 × 100%；同一患者在统计窗口内就诊 ≥2 次，首诊后每次计复诊；"
                   "基线 62.42%（全期），按窗口重算而非简单求和。",
        "ref": "《指标口径手册》4.5 / 评审 R-07",
    },
    {
        "title": "M32 检验阳性率口径",
        "keywords": ["阳性率", "检验阳性", "M32"],
        "content": "M32 检验阳性率 = 异常类报告数 ÷ 检验报告总数 × 100%；异常类 = {阳性, 偏高, 偏低, 异常}；基线 30.74%。",
        "ref": "《指标口径手册》4.5",
    },
    {
        "title": "三种口径的区别（登记 / 流水 / 财务）",
        "keywords": ["口径", "登记口径", "流水口径", "财务口径", "区别"],
        "content": "登记口径：就诊登记时的费用汇总（fee_amount / total_fee），用于次均费用；"
                   "流水口径：逐笔收费明细汇总（amount），用于收入类指标；"
                   "财务口径：财务日报（revenue / drug_revenue / consumable_revenue），用于药占比、耗占比与对账。"
                   "三者不可混算，每个指标在手册台账中标注了来源。",
        "ref": "《指标口径手册》2.2",
    },
    {
        "title": "为什么有些指标显示「数据源待补充」",
        "keywords": ["待补充", "PENDING", "预约率", "退号率", "死亡率", "缺失"],
        "content": "M04 门诊预约率、M05 门诊退号率、M27 低风险组死亡率因源数据缺少预约标识、退号标识与死亡/风险分级字段，"
                   "结果表记 NULL 且 data_status=PENDING，不进入看板结论与考核；接入相应数据源后自动启用。",
        "ref": "《指标口径手册》第 6 章 K8 / 评审 R-09",
    },
    {
        "title": "数据更新时点（T+1）",
        "keywords": ["更新", "什么时候", "时效", "T+1", "刷新"],
        "content": "平台以 T+1 日终批为主：每日 02:00 触发采集→清洗→质检→宽表→DWS/集市→指标计算，"
                   "关键指标支持小时级增量；接口层对驾驶舱数据做 5 分钟缓存。",
        "ref": "《概要设计》4.3 / 《部署运维手册》8.5",
    },
    {
        "title": "数据权限与可见范围",
        "keywords": ["权限", "看不到", "数据范围", "科室用户", "越权"],
        "content": "RBAC 三角色：管理员（全院 + 系统管理）、运营分析师（全院分析）、科室用户（仅本科室）。"
                   "科室用户查询自动限定本科室维度，不可查看全院汇总（ALL）与管理页；越权返回 403/40302。",
        "ref": "《需求规格说明书》2.2 / 《用户操作手册》2.3",
    },
    {
        "title": "看板数值与财务/月报不一致怎么办",
        "keywords": ["不一致", "对不上", "财务", "月报", "差异"],
        "content": "先确认口径：药占比、耗占比默认财务口径，收入类为流水口径；两口径在模拟数据中相差约 6.36%。"
                   "看板提供口径切换开关；对账规则 QR-REC-01 容差 ±10%。",
        "ref": "《指标口径手册》K2 / 《测试计划与报告》3.4",
    },
    {
        "title": "报表导出支持哪些格式",
        "keywords": ["导出", "excel", "xlsx", "pdf", "下载"],
        "content": "支持 Excel（xlsx）与 PDF 导出：`GET /api/dashboard/export?format=xlsx|pdf`，"
                   "单次导出上限 20,000 行；报表中心支持按维度组合查询后导出并留存导出审计。",
        "ref": "《用户操作手册》8.5 / 《部署运维手册》配置项",
    },
    {
        "title": "自然语言问数能问什么",
        "keywords": ["问数", "自然语言", "怎么问", "提问", "NL2SQL"],
        "content": "支持 33 项指标 × 11 个科室维度 × 三种时间粒度（日/月/全期）的查询与对比，例如"
                   "「上月呼吸科床位使用率趋势如何」「本季度各科室门诊人次排名」「6月的药占比是多少」。"
                   "不支持跨库任意 SQL、明细患者级查询与预测类问题。",
        "ref": "《大模型应用设计说明》第 3 章 / 《用户操作手册》10 章",
    },
    {
        "title": "DRG 分组是真实分组吗",
        "keywords": ["DRG 模拟", "分组器", "真实分组", "权重来源"],
        "content": "当前使用 dim_disease 中的模拟 DRG 分组与权重（10 个病种对应 10 个组），用于跑通入组率、CMI 与消耗指数链路；"
                   "生产环境须替换为院方 DRG/DIP 分组器结果表，公式不变。",
        "ref": "《指标口径手册》K3 / 评审 R-01",
    },
    {
        "title": "科室业务量为什么都差不多",
        "keywords": ["科室均衡", "业务量差不多", "均匀", "排序"],
        "content": "模拟数据集为均匀抽样（每科室 900 门诊人次、150 出院人次），因此科室对比类图表仅用于功能演示，"
                   "不得作为科室绩效排序结论。",
        "ref": "《指标口径手册》K4",
    },
    {
        "title": "部署与启动方式",
        "keywords": ["部署", "启动", "docker", "容器", "nginx"],
        "content": "`docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build` 一键启动"
                   "mysql / backend / frontend / nginx 四个服务；Nginx 托管前端静态资源并将 /api 反代到后端 8000。",
        "ref": "《部署运维手册》第 6、7 章",
    },
]


def _score(question: str, snippet: dict[str, Any]) -> int:
    """关键词命中打分（长关键词权重更高）。"""
    score = 0
    for keyword in snippet["keywords"]:
        if keyword.lower() in question.lower():
            score += len(keyword)
    return score


def retrieve(question: str, top_k: int = 2) -> list[dict[str, Any]]:
    """检索手册片段（按命中分数降序）。"""
    scored = [(snippet, _score(question, snippet)) for snippet in KB_SNIPPETS]
    hits = [(snippet, score) for snippet, score in scored if score > 0]
    hits.sort(key=lambda item: item[1], reverse=True)
    return [snippet for snippet, _score_value in hits[:top_k]]


def kb_answer(question: str, *, use_llm: bool = True) -> dict[str, Any]:
    """手册分块检索 + 模型组织答案；未命中时明确告知。"""
    if not question or not question.strip():
        raise ValueError("问题不能为空")

    snippets = retrieve(question)
    if not snippets:
        return {
            "question": question,
            "answer": "手册中未收录该口径，建议查阅《指标口径手册》第 4 章指标明细或联系数据管理组确认。",
            "refs": [],
            "matched": False,
            "source": "none",
        }

    fallback_answer = "；".join(f"{item['title']}：{item['content']}" for item in snippets)
    answer = fallback_answer
    source = "manual_snippet"

    client = get_client()
    if use_llm and client.is_available:
        payload, _call = client.chat_json(build_kb_prompt(question, snippets))
        if payload and payload.get("answer"):
            answer = str(payload["answer"])
            source = "llm"

    return {
        "question": question,
        "answer": answer,
        "refs": [{"title": item["title"], "ref": item["ref"]} for item in snippets],
        "matched": True,
        "source": source,
    }


__all__ = ["KB_SNIPPETS", "retrieve", "kb_answer"]
