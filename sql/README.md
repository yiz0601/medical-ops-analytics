# sql —— 数仓与业务库脚本

按 DIM → ODS → DWD → DWS → ADS 分层组织建表与加工脚本。
数据库：MySQL 8.0，库名 `medical_ops`，字符集 `utf8mb4`，引擎 `InnoDB`。

> **生成方式**：`dim/dim_tables.sql`（含初始化数据）与 `ods/dwd/dws/ads/*_tables.sql`
> 均由 `backend/etl/jobs/export_ddl.py` 从 Python 表结构（`backend/etl/config/*_schema.py`）与
> 维表数据（`dim_seed.py`）自动生成，保证「代码结构 = 数据库结构」。
> **修改表结构请改 Python 定义后重新生成**，不要手工编辑这些 SQL 文件。

```bash
cd backend
python -m etl.jobs.export_ddl              # 重新生成全部五层脚本
python -m etl.jobs.export_ddl --layer dim  # 仅重新生成维表脚本
```

## 目录职责与交付状态

| 目录 | 职责 | 脚本 | 状态 |
| --- | --- | --- | --- |
| `dim/` | 6 张公共维表（科室/日期/病种/收费类别/DRG 分组/号别）+ 初始化数据 | `dim_tables.sql`（19 条语句） | ✅ 阶段三 |
| `ods/` | 6 张贴源表（含 3 个 ETL 元数据字段）+ 结构与行数校验 | `ods_tables.sql`、`verify_ods.sql` | ✅ 阶段二 |
| `dwd/` | 8 张明细表：6 张分源明细 + `dwd_visit_detail`（就诊宽表）+ 收费宽表 | `dwd_tables.sql` | ✅ 阶段二/三 |
| `dws/` | 1 张宽汇总表 `dws_dept_daily`（科室 × 日期，主键唯一） | `dws_tables.sql` | ✅ 阶段三 |
| `ads/` | 8 张主题集市表 + 指标结果表 `ads_indicator_result` | `ads_tables.sql` | ✅ 阶段三 |

## 建库与执行顺序

```sql
CREATE DATABASE IF NOT EXISTS medical_ops
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;
USE medical_ops;
```

```
dim（维表 + 初始化数据）
  → ods（贴源建表） → ETL 采集入库
    → dwd（清洗脱敏 + 宽表加工）
      → dws（科室 × 日期汇总）
        → ads（8 集市 + 指标结果）
```

```bash
# 1) 建表与初始化（MySQL 8.0）
mysql -h127.0.0.1 -P3306 -uroot -p < sql/dim/dim_tables.sql
mysql -h127.0.0.1 -P3306 -uroot -p < sql/ods/ods_tables.sql
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/dwd/dwd_tables.sql
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/dws/dws_tables.sql
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/ads/ads_tables.sql

# 2) ODS 结构与行数校验（6 张表存在，行数 9000/1500/44078/1500/2934/910）
mysql -h127.0.0.1 -P3306 -uroot -p medical_ops < sql/ods/verify_ods.sql

# 3) 全链路加工（8 个任务：维表 → 采集 → 清洗 → 质检 → 宽表 → DWS/集市 → 指标 → 对账）
cd backend
python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30
```

## 校验基线（各脚本末尾内置校验段，可直接执行）

| 层 | 校验内容 | 期望值 |
| --- | --- | --- |
| DIM | `dim_department` / `dim_date` / `dim_disease` / `dim_fee_type` / `dim_drg_group` / `dim_visit_type` | 14 / 821 / 10 / 10 / 10 / 5 行；统计期 91 天；开放床位合计 177 |
| ODS | 6 张贴源表行数 | 9,000 / 1,500 / 44,078 / 1,500 / 2,934 / 910 |
| DWD | 分源明细 6 张 + 就诊宽表 + 收费宽表 | 同上 6 个；`dwd_visit_detail` = 10,500；`dwd_charge_detail` = 44,078 |
| DWS | `dws_dept_daily` | 910 行（10 科室 × 91 天），主键唯一 |
| ADS | 8 张主题集市 | 各 910 行；`ads_indicator_result` 唯一键（指标编码+维度值+粒度+统计日期）无重复 |

> 说明：ODS 表以源系统对象命名（`ods_<系统>_<对象>`），DWD 明细统一以 `_detail` 结尾；
> 重跑与回刷按 `etl_batch_date`（同批次）先删后插，避免重复累加；各表均带
> `etl_batch_date`、`etl_batch_id`、`etl_load_time` 三个元数据字段。
