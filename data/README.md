# data —— 模拟数据集与样例文件

本目录存放平台使用的模拟业务数据，来源于项目下发的《医疗运营数据主题分析平台数据集》，**已原样解压入库，未做任何改写**。

## 一、目录与文件清单

```
data/
├── mock_his/                     # 模拟 HIS / EMR / LIS 业务数据（源系统导出风格 CSV）
│   ├── his_outpatient.csv        # HIS 门诊挂号就诊表        9,000 行 / 11 列
│   ├── his_inpatient.csv         # HIS 住院入出院表          1,500 行 / 16 列
│   ├── his_charge.csv            # HIS 收费明细流水         44,078 行 /  9 列
│   ├── emr_record.csv            # EMR 病历首页摘要           1,500 行 /  7 列
│   └── lis_report.csv            # LIS 检验报告              2,934 行 /  6 列
└── files/                        # Excel/CSV 报表文件（文件接入通道）
    └── finance_excel.csv         # 财务日报（科室×日）         910 行 /  5 列
```

统一统计时间窗：**2025-04-01 ~ 2025-06-30（91 天）**；编码 UTF-8、含表头、逗号分隔。

## 二、文件与 ODS 目标表映射

| 源文件 | 源系统类型 | ODS 目标表 | 采集方式 | 调度周期 |
| --- | --- | --- | --- | --- |
| `his_outpatient.csv` | HIS（MySQL） | `ods_his_outpatient_visit` | JDBC 全量抽取 | T+1 日终批 |
| `his_inpatient.csv` | HIS（MySQL） | `ods_his_inpatient_visit` | JDBC 全量抽取 | T+1 日终批 |
| `his_charge.csv` | HIS（MySQL） | `ods_his_charge_detail` | JDBC 按 `fee_date` 增量抽取 | T+1 日终批 / 小时增量 |
| `emr_record.csv` | EMR（Oracle） | `ods_emr_record` | JDBC 全量抽取 | T+1 日终批 |
| `lis_report.csv` | LIS（SQLServer） | `ods_lis_report` | JDBC 按 `report_date` 增量抽取 | T+1 日终批 / 小时增量 |
| `finance_excel.csv` | 财务系统导出文件 | `ods_finance_excel` | 文件上传 + 模板校验解析 | T+1 日终批（人工上传，支持定时目录扫描） |

> 5 类数据源（HIS / EMR / LIS / 财务 / 文件通道）实现"接入不少于 5 类数据源"的目标。

## 三、字段说明与主键

| 文件 | 主键 | 关键字段 | 备注 |
| --- | --- | --- | --- |
| his_outpatient.csv | `visit_id` | `patient_id, dept_code, visit_date, visit_type, fee_amount` | `visit_type` ∈ 普通/专家/急诊 |
| his_inpatient.csv | `visit_id` | `dept_code, bed_no, admit_date, discharge_date, stay_days, total_fee, drug_fee, consumable_fee, disease_code` | `stay_days = discharge_date - admit_date`；含 17 例当日出入院 |
| his_charge.csv | `charge_id` | `visit_id, visit_type, fee_date, fee_type_code, amount` | 覆盖 10,500 个就诊号；费别 9 类 |
| emr_record.csv | `record_id` | `visit_id, diagnosis, disease_code` | ICD-10 主诊断；覆盖住院就诊 |
| lis_report.csv | `report_id` | `visit_id, item_name, result_text` | 检验项目 8 项；结果 4 类判定 |
| finance_excel.csv | `record_id` | `stat_date, dept_code, revenue, drug_revenue, consumable_revenue` | 10 科室 × 91 天 = 910 行，`(stat_date, dept_code)` 唯一 |

**隐私字段**：`patient_name`、`id_card`、`phone` 为模拟数据，进入 DWD 层前必须脱敏（见《指标口径手册》与《概要设计》）。

## 四、已知数据特征（ETL 与指标计算必须理解）

1. **两条收入路径独立生成**：`his_outpatient.fee_amount` / `his_inpatient.total_fee`（就诊登记汇总口径）与 `his_charge`（收费流水口径）不满足强对账关系。各指标的数据来源在《指标口径手册》中逐项标注，请勿混用。
2. **财务口径 vs 流水口径差异约 6.4%**（41,446,631.11 元 vs 44,260,283.80 元），在 ±10% 容差内。
3. **无 DRG 分组器输出**：病种类指标通过 `dim_drg_group` 做模拟分组映射。
4. **科室业务量均匀**：每个科室 900 门诊人次、150 出院人次，系均匀抽样结果。
5. 住院数据含 17 例当日出入院（`stay_days = 0`），平均住院日统计需说明。

## 五、使用约束

- 本目录数据仅用于系统开发、演示与验收测试，**不得用于真实诊疗或对外披露**。
- 容器部署时以只读方式挂载到 `/app/data`（见 `deploy/docker-compose.yml`）。
- 重新导入数据请执行（阶段二已交付）：

  ```bash
  cd backend
  python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30
  ```

  批次信息写入 `etl_batch_date` / `etl_batch_id` / `etl_load_time`；同批次重跑自动先删后插（幂等）；
  质量报告输出到 `backend/etl/logs/quality_report_YYYYMMDD.json`。
