# 医疗运营数据主题分析平台（medical-ops-analytics）

面向医院运营管理部门的一站式数据分析平台：整合 HIS、EMR、LIS、财务等多源业务数据，构建运营主题数据仓库，
提供指标计算、多维分析、可视化看板与大模型智能问数服务，辅助管理者实现数据驱动的精细化运营决策。

> 当前阶段：**工程骨架 + 模拟数据集 + 交付文档** 已就绪；后端接口、ETL 任务、数仓 SQL、前端页面按《项目开发流程》七大阶段逐步实现。

## 一、快速了解

| 项 | 内容 |
| --- | --- |
| 技术栈 | Python 3.11 + FastAPI · MySQL 8.0 · Vue 3 + ECharts 5 · Docker Compose · Nginx · LLM（NL2SQL） |
| 数仓分层 | ODS（贴源）→ DWD（明细）→ DWS（汇总）→ ADS（应用），辅以 DIM 公共维表 |
| 数据规模 | 门诊 9,000 人次 · 住院 1,500 人次 · 收费明细 44,078 行 · 检验 2,934 份 · 财务日报 910 行（2025-04-01 ~ 06-30，91 天，10 个科室） |
| 核心能力 | ≥5 类数据源接入 · ≥30 项运营指标 · 8 个分析主题 · 3 套看板 · ≥10 类图表组件 · NL2SQL 问数与报告生成 · ≥95% 质量规则覆盖 |
| 部署形态 | `docker compose up` 一键启动 MySQL + 后端 + 前端（Nginx） |

## 二、工程目录结构

```
medical-ops-analytics/                 # 本工程根目录
├── backend/                           # 后端服务（Python FastAPI）
│   ├── app/
│   │   ├── main.py                    # 应用入口（已就绪：健康检查 + 路由注册位）
│   │   ├── core/                      # 配置、鉴权、依赖注入、统一响应与异常
│   │   ├── api/                       # RESTful 接口层（按模块拆分路由）
│   │   ├── models/                    # ORM 数据模型
│   │   ├── schemas/                   # Pydantic 请求/响应模型
│   │   ├── services/                  # 业务逻辑（指标查询、报表、导出）
│   │   └── llm/                       # 大模型对接（NL2SQL、报告生成、Prompt 模板）
│   ├── etl/
│   │   ├── config/                      # ✅ 阶段二：settings / dicts / ods_schema / dwd_schema
│   │   │                                #    source_config（数据源注册）/ loader / baseline / sources.json
│   │   ├── jobs/                        # ✅ 阶段二：extract_ods（采集+装载）/ clean_dwd（清洗脱敏 + DWD 宽表）
│   │   │                                #    quality_check（5 类规则+报告）/ run_all（总入口）
│   │   │                                # ✅ 阶段三：init_dim（维表）/ aggregate_dws（DWS+8 集市）
│   │   │                                #    ads_indicators（33 项指标+对账）/ export_ddl（生成 MySQL DDL）
│   │   ├── scheduler/                   # ✅ 阶段二：scheduler.py（注册/重试/编排/定时/日志）
│   │   └── quality/                     # 阶段三起：规则引擎与报告模块拆分
│   ├── requirements.txt                 # 已就绪
│   └── tests/                           # ✅ 阶段二：test_etl_smoke.py（冒烟 + 指标基线断言）
├── frontend/                          # 前端应用（Vue3 + ECharts）
│   ├── src/
│   │   ├── api/                       # 接口封装
│   │   ├── views/                     # 看板/报表/管理页面
│   │   ├── components/                 # 图表与通用组件
│   │   ├── router/                    # 路由
│   │   ├── store/                     # 状态管理（Pinia）
│   │   └── utils/                     # 工具函数
│   ├── package.json                   # 已就绪
│   └── vite.config.js                 # 已就绪（含 /api 开发代理）
├── sql/                               # 数仓与业务库脚本
│   ├── ods/  dwd/  dws/  ads/  dim/   # 分层建表与加工脚本（阶段三交付）
│   └── README.md                      # 分层职责与执行顺序
├── data/                              # 模拟数据与样例文件
│   ├── mock_his/                      # HIS/EMR/LIS 模拟数据（5 个 CSV）
│   ├── files/                         # 财务日报文件（Excel/CSV 通道）
│   └── README.md                      # 文件清单、字段、ODS 映射
├── docs/                              # 项目文档（10 份，见下表）
├── deploy/                            # 部署配置
│   ├── docker-compose.yml             # 已就绪
│   ├── Dockerfile.backend             # 已就绪
│   ├── Dockerfile.frontend            # 已就绪
│   └── nginx.conf                     # 已就绪
└── README.md                          # 本文件
```

## 三、文档索引（docs/）

| 文档 | 说明 | 主要读者 |
| --- | --- | --- |
| [项目说明](docs/项目说明.md) | 项目概述、目标、模块划分、业务流程、成果物清单 | 全体 |
| [项目开发流程](docs/项目开发流程.md) | 7 个阶段 × 20 项单元任务的开发路线与交付物 | 开发/管理 |
| [培养目标](docs/培养目标.md) | 能力矩阵、阶段任务映射、考核方式 | 学员/指导老师 |
| [需求规格说明书](docs/需求规格说明书.md) | 角色、功能需求、非功能需求、验收标准 | 需求/开发/测试 |
| [概要设计](docs/概要设计.md) | 总体架构、分层设计、模块划分、接口与部署概要 | 开发 |
| [详细设计](docs/详细设计.md) | 表结构、指标 SQL、接口契约、页面与组件设计 | 开发 |
| [指标口径手册](docs/指标口径手册.md) | 30+ 项指标口径、公式、来源、维度、粒度 | 数据/业务/开发 |
| [测试计划与报告](docs/测试计划与报告.md) | 测试策略、用例、缺陷与测试结论 | 测试 |
| [部署运维手册](docs/部署运维手册.md) | 环境要求、容器部署、运维巡检、故障处理 | 运维 |
| [用户操作手册](docs/用户操作手册.md) | 角色权限、看板与报表操作、智能问数使用 | 业务用户 |

> 协作规范见 [CONTRIBUTING.md](CONTRIBUTING.md)：main 受保护，变更一律经 Fork/特性分支 + Pull Request 合入。

## 四、快速开始

### 1. 本地开发

```bash
# 后端
cd backend
python -m venv .venv && .venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 接口文档：http://127.0.0.1:8000/docs

# 前端
cd frontend
npm install
npm run dev
# 访问：http://127.0.0.1:5173
```

### 2. 数据采集与整合（阶段二，已交付）

```bash
cd backend
pip install -r requirements.txt          # pandas / SQLAlchemy / PyMySQL 为 ETL 依赖

# 一键跑通：采集 -> 清洗 -> 质量校验（写入 ODS/DWD，产出质量报告）
python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30

# 仅核对 ODS 行数与基线（9000/1500/44078/1500/2934/910）
python -m etl.jobs.run_all --verify

# 冒烟测试（临时库，含幂等性与指标基线复算断言）
python -m tests.test_etl_smoke
```

数据库连接：设置 `MOA_DB_URL`（如 `mysql+pymysql://moa:pwd@127.0.0.1:3306/medical_ops?charset=utf8mb4`）
或 `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME`；未配置时自动回退 SQLite 文件库
`backend/etl/logs/moa_dev.db`，用于无 MySQL 环境下的链路验证。

产物：`backend/etl/logs/task_run.log`（任务日志）、
`backend/etl/logs/quality_report_YYYYMMDD.json`（质量报告：25 条规则、评分、覆盖率、告警清单）。

### 3. 数据仓库与指标计算（阶段三，已交付）

```bash
cd backend

# 生成 MySQL DDL（维表含初始化数据；ODS/DWD/DWS/ADS 由表结构自动生成）
python -m etl.jobs.export_ddl
mysql -h127.0.0.1 -uroot -p < sql/dim/dim_tables.sql    # 依次 dim/ods/dwd/dws/ads

# 单独执行各阶段（也可直接用 run_all 串跑全部 8 个任务）
python -m etl.jobs.init_dim                       # 公共维表（6 张：科室14/日期821/病种10/收费类别10/DRG10/号别5）
python -m etl.jobs.clean_dwd                      # DWD 分源明细 + 就诊/收费宽表（10500 / 44078 行）
python -m etl.jobs.aggregate_dws                  # DWS 汇总（910 行）+ 8 大主题集市（各 910 行）
python -m etl.jobs.ads_indicators                 # 33 项指标写入 ads_indicator_result + 手工 SQL 对账
```

指标结果：`ads_indicator_result`（唯一键 = 指标编码 + 维度值 + 粒度 + 统计日期）；
对账记录：`backend/etl/logs/indicator_reconcile_YYYYMMDD.json`；指标运行日志：`backend/etl/logs/indicator_run.log`。

### 4. 容器化部署

```bash
cp deploy/.env.example deploy/.env      # 按需修改数据库口令、JWT 密钥、LLM Key
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
# 访问：http://<服务器IP>/          健康检查：http://<服务器IP>/health
```

> `deploy/.env.example` 已提供；`sql/` 下 ODS/DWD 建表脚本已交付（阶段二），
> DIM/DWS/ADS 脚本与数据库初始化编排见《部署运维手册》。

## 五、默认账号

| 账号 | 密码 | 角色 | 数据范围 |
| --- | --- | --- | --- |
| `admin` | `Admin@123` | 管理员 | 全院 |
| `analyst01` | `Analyst@123` | 运营分析师 | 全院（只读分析 + 报表） |
| `dept_hn` | `Dept@123` | 科室用户（呼吸内科） | 仅本科室 |

> 密码为演示环境初始值，上线前必须修改；详见《部署运维手册》安全加固章节。

## 六、阶段进度

- [x] 阶段一：项目准备 —— 目录骨架、模拟数据入库、文档体系
- [x] 阶段二：多源数据采集与整合 —— ODS 建表、ETL 任务、DWD 清洗、质量校验（6 张 ODS + 6 张 DWD 落库，行数与基线一致；25 条质量规则评分 92.0、字段覆盖率 100%）
- [x] 阶段三：数据仓库建模与指标计算 —— DIM 6 表 / DWD 宽表 / DWS 汇总 / 8 大主题集市 / **33 项指标（M01–M33）**，11 项核心指标命中基线，10 项手工 SQL 对账误差 ≤ 0.00003
- [ ] 阶段四：后端服务开发 —— 认证鉴权、指标查询、多维分析、导出
- [ ] 阶段五：前端可视化开发 —— 10 类图表组件、3 套看板
- [ ] 阶段六：智能分析与大模型对接 —— NL2SQL、报告生成、异常归因
- [ ] 阶段七：系统测试与部署验收 —— 用例、缺陷闭环、容器化部署

## 七、数据使用声明

`data/` 下全部数据为模拟数据（患者姓名、身份证号、手机号均为生成值），仅用于系统开发、演示与验收，
**不得用于真实诊疗决策或对外披露**。
