# 协作规范（CONTRIBUTING）

本文件约定「医疗运营数据主题分析平台」的分支模型、提交规范、PR 流程与评审标准。
适用于所有协作者（含通过 Fork 提交贡献的外部成员）。

## 一、协作模式：受保护分支 + Fork/PR

`main` 为受保护分支，**不接受任何直接 push**，所有变更必须经 Pull Request 合入。

### 1. 仓库维护者需在 GitHub 上完成的一次性设置

Settings → Branches → Add branch protection rule（分支名 `main`）：

- [x] Require a pull request before merging
- [x] Require approvals：**1**（成员 ≥3 人时建议 2）
- [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require conversation resolution before merging
- [x] Require linear history（保持提交历史线性）
- [x] Do not allow bypassing the above settings（管理员同样受约束）
- [x] Restrict who can push to matching branches（仅维护者可合并）
- [ ] Allow force pushes / Allow deletions（**均保持关闭**）

Settings → General → Pull Requests：

- [x] Allow squash merging（推荐默认，一个 PR 一个提交）
- [ ] Allow merge commits（可选关闭）
- [x] Automatically delete head branches

### 2. 协作者如何提交（Fork 流程）

```bash
# 1) 在 GitHub 上 Fork 本仓库到你自己的账号，然后克隆
git clone https://github.com/<你的账号>/medical-ops-analytics.git
cd medical-ops-analytics
git remote add upstream https://github.com/<维护者账号>/medical-ops-analytics.git

# 2) 从最新 main 拉出特性分支（分支名见下文规范）
git fetch upstream && git checkout -b feature/T03-datasource-registry upstream/main

# 3) 开发并提交（提交信息规范见第三节）
git add -A && git commit -m "feat(etl): 实现数据源注册与连接测试 (#T03)"

# 4) 推送前先同步上游，避免冲突
git fetch upstream && git rebase upstream/main

# 5) 推送到自己的 Fork，然后在 GitHub 上发起 Pull Request 到 upstream/main
git push -u origin feature/T03-datasource-registry
```

> 若维护者已把你加为 **Write 协作者**：可跳过 Fork，直接克隆本仓库并推特性分支，`main` 仍受保护。

## 二、分支模型

| 分支 | 用途 | 来源 → 合入 | 命名 |
| --- | --- | --- | --- |
| `main` | 可交付主干，始终可运行 | — | 固定 |
| `feature/*` | 新功能 / 单元任务 | `main` → PR → `main` | `feature/T{01-20}-{短名}` |
| `fix/*` | 缺陷修复 | `main` → PR → `main` | `fix/{缺陷号或简述}` |
| `release/*` | 阶段验收冻结（阶段七） | `main` → 验收 → `main` + tag | `release/v{版本}` |
| `hotfix/*` | 生产紧急修复 | `main` → PR → `main` | `hotfix/{简述}` |

分支名中的任务号对齐《项目开发流程》第 4 章 **T01–T20**，例如
`feature/T04-ods-load`、`feature/T09-metric-calc`。

## 三、提交信息规范

格式：`type(scope): 描述 (#T{任务号})`

| type | 含义 | type | 含义 |
| --- | --- | --- | --- |
| feat | 新功能 | docs | 文档 |
| fix | 缺陷修复 | test | 测试 |
| refactor | 重构（不改行为） | chore | 构建/配置/杂项 |
| perf | 性能优化 | style | 格式（不影响逻辑） |

scope 取值：`etl` / `sql` / `api` / `ui` / `ai` / `docs` / `deploy`。

示例：

```
feat(etl): 实现 ODS 幂等装载与串跑入口 (#T04)
fix(etl): 源 CSV 含 BOM 导致表头校验失败 (#T04)
docs(metric): 补充 M25/M26 模拟标化基准说明
```

要求：一条提交只做一件事；描述用中文、动词开头、不超过 50 字；涉及口径变更须在正文写明影响指标编号。

## 四、PR 流程与评审标准

1. 发起 PR 到 `main`，标题同提交信息规范，描述按 `.github/pull_request_template.md` 填写。
2. CI/自检：本地至少通过 `python -m tests.test_etl_smoke`（涉及 ETL/SQL）或对应模块测试。
3. 评审人按下列清单逐项确认，**任一项不通过则 Request changes**：

| 检查项 | 要求 |
| --- | --- |
| 口径一致性 | 指标编号、公式、数据来源与《指标口径手册》一致，无自造口径 |
| 数据安全 | DWD 及之后无隐私明文；日志/异常不打印身份证、手机号、患者姓名 |
| 幂等性 | 涉及入库的变更按 `etl_batch_date` 先删后插，重跑不产生重复数据 |
| 数据质量 | 行数与基线（9000/1500/44078/1500/2934/910）一致，质量报告无新增阻断项 |
| 命名规范 | 表前缀 `ods_/dwd_/dws_/ads_/dim_`，DWD 以 `_detail` 结尾；接口 `/api/v1` |
| 测试 | 新增/修改逻辑有断言覆盖，测试通过 |
| 文档 | 影响口径、接口、部署的变更同步更新 `docs/` 对应文档 |
| 无死代码 | 无调试输出残留（`print` 仅用于 ETL 运行日志）、无临时文件 |

4. 合并方式：**Squash merge**；合并后删除源分支。
5. `main` 上禁止提交临时调试代码；禁止提交 `deploy/.env`、密钥、`backend/etl/logs/` 产物。

## 五、目录与命名速查

```
backend/etl/config/      表结构、字典、数据源、连接与基线
backend/etl/jobs/        采集/清洗/质检/总入口脚本
backend/etl/scheduler/   任务注册、重试、依赖编排、定时
sql/ods|dwd|dws|ads|dim  分层建表与加工脚本
docs/                    10 份交付文档（口径变更须同步）
deploy/                  Docker Compose / Dockerfile / Nginx
```

## 六、本地开发与自检

```bash
cd backend
pip install -r requirements.txt
python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30   # 采集→清洗→质检
python -m etl.jobs.run_all --verify                              # 行数基线核对
python -m tests.test_etl_smoke                                   # 41 项断言
```

数据库连接通过 `MOA_DB_URL` 或 `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME` 指定；
未配置时回退 SQLite（`backend/etl/logs/moa_dev.db`），便于无 MySQL 环境验证。
