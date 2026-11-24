"""回刷工具（阶段七 · 步骤 3）。

    backfill(start_date, end_date)   按区间重跑 ODS → DWD → DWS/ADS 加工链，返回各层影响行数

用途：口径变更、补数、窗口修正后按历史区间重刷；所有写入均按批次先删后插（幂等）。
注意：ODS 采集本身按源文件全量抽取，回刷只重跑加工链路。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.engine import Engine

from etl.config.settings import get_engine, normalize_batch_date


def backfill(
    start_date: str,
    end_date: str,
    *,
    engine: Engine | None = None,
    batch_date: date | str | None = None,
    include_dim: bool = False,
) -> dict[str, Any]:
    """按区间重跑加工链（DWD → 宽表 → DWS/集市 → 指标），返回各层行数。"""
    from etl.jobs.ads_indicators import run_indicators
    from etl.jobs.aggregate_dws import build_dws_daily, build_theme_marts
    from etl.jobs.clean_dwd import run_clean_all, run_wide_tables

    eng = engine or get_engine()
    bd = normalize_batch_date(batch_date or end_date)
    print(f"[回刷] 区间 {start_date} ~ {end_date}，批次 {bd}（先删后插，幂等）")

    result: dict[str, Any] = {"date_range": [start_date, end_date], "batch_date": str(bd)}

    if include_dim:
        from etl.jobs.init_dim import init_dim

        result["dim"] = init_dim(eng)

    result["dwd"] = run_clean_all(bd, engine=eng)
    result["dwd_wide"] = run_wide_tables(start_date, end_date, bd, engine=eng)
    result["dws"] = {"dws_dept_daily": build_dws_daily(batch_date=bd, engine=eng)}
    result["dws"].update(build_theme_marts(batch_date=bd, engine=eng))
    result["ads"] = {
        "month": run_indicators(start_date, end_date, "month", engine=eng, batch_date=bd)["rows"],
        "period": run_indicators(start_date, end_date, "period", engine=eng, batch_date=bd)["rows"],
    }

    dwd_rows = sum(result["dwd"].values()) if isinstance(result["dwd"], dict) else 0
    dws_rows = sum(result["dws"].values())
    ads_rows = sum(result["ads"].values())
    result["summary"] = {
        "dwd_rows": dwd_rows,
        "dws_rows": dws_rows,
        "ads_rows": ads_rows,
        "total_rows": dwd_rows + dws_rows + ads_rows,
    }
    print(
        f"[回刷] 完成：DWD {dwd_rows} 行 / DWS+集市 {dws_rows} 行 / 指标 {ads_rows} 行"
        f"（合计 {result['summary']['total_rows']}）"
    )
    return result


if __name__ == "__main__":  # 手工执行：python -m etl.jobs.backfill
    import sys

    from etl.config.baseline import STAT_PERIOD

    start = sys.argv[1] if len(sys.argv) > 1 else STAT_PERIOD[0]
    end = sys.argv[2] if len(sys.argv) > 2 else STAT_PERIOD[1]
    backfill(start, end)
