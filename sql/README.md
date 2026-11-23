# sql —— 数仓与业务库脚本

按 ODS → DWD → DWS → ADS 分层组织建表与加工脚本，公共维表与字典初始化放 `dim/`。
数据库：MySQL 8.0，库名 `medical_ops`，字符集 `utf8mb4`，引擎 `InnoDB`。

## 目录职责与交付状态

| 目录 | 职责 | 脚本 | 状态 |
| --- | --- | --- | --- |
| `ods/` | 贴源层建表（6 表，含 3 个 ETL 元数据字段）、结构与行数校验 | `ods_tables.sql`、`verify_ods.sql` | ✅ 阶段二已交付 |
| `dwd/` | 明细层建表（6 表，含脱敏列与派生列）、DWD 校验 | `dwd_tables.sql` | ✅ 阶段二已交付 |
| `dws/` | 汇总层：按主题 + 时间粒度聚合（日/月） | `dws_tables.sql`、`dws_aggregate.sql` | ⏳ 阶段三 |
| `ads/` | 应用层指标结果表，供后端直接查询 | `ads_tables.sql`、`ads_kpi_calc.sql`、`ads_dashboard.sql` | ⏳ 阶段三 |
| `dim/` | 公共维表与字典初始化：科室、费别、号别、病种、DRG 分组、日期 | `01_dim_dept.sql`、`02_dim_fee_type.sql`、`03_dim_disease_drg.sql`、`04_dim_date.sql` | ⏳ 阶段三 |

> 阶段二的维度字典当前以 Python 常量维护（`backend/etl/config/dicts.py`：科室 10 个 / 费别 9 类 /
> 病种与模拟 DRG 分组 10 组），待阶段三落 `dim/` SQL 后改为读取维表；口径与《指标口径手册》第 7 章一致。

## 建库脚本

```sql
CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE medical_ops;
```

## 执行顺序

```
dim（维表与字典，阶段三）
  → ods（贴源建表）          ← sql/ods/ods_tables.sql
    → ETL 采集入库            ← cd backend && python -m etl.jobs.run_all
      → dwd（清洗脱敏加工）    ← sql/dwd/dwd_tables.sql（建表）+ etl.jobs.clean_dwd（加工）
        → dws（主题汇总，阶段三）
          → ads（指标结果，阶段三）
```

## 执行命令

```bash
# 1) 建表（MySQL 8.0）
mysql -h127.0.0.1 -P3306 -uroot -p < sql/ods/ods_tables.sql
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/dwd/dwd_tables.sql

# 2) ODS 结构与行数校验（预期 6 张表存在，行数 9000/1500/44078/1500/2934/910）
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/ods/verify_ods.sql

# 3) 采集与清洗（日志与质量报告写入 backend/etl/logs/）
cd backend
python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30
```

> 注意：ODS 表以源系统对象命名（`ods_<系统>_<对象>`），DWD 明细表统一以 `_detail` 结尾；
> 重跑与回刷按 `etl_batch_date`（同批次）先删后插，避免重复累加；每张表均带
> `etl_batch_date`、`etl_batch_id`、`etl_load_time` 三个元数据字段。
