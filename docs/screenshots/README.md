# 运营看板截图采集说明

本目录用于存放《成果物清单》中"应用类 → 运营看板截图"要求的页面截图。
**当前状态：待采集**（开发机无浏览器环境，截图需在有浏览器的机器上执行一次）。

## 一、采集前置条件

1. 后端已启动且数据已装载（指标结果表有数据）：

   ```bash
   cd backend
   python -m etl.jobs.run_all --start 2025-04-01 --end 2025-06-30
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. 前端已启动（开发模式自带 `/api` 代理）：

   ```bash
   cd frontend
   npm install
   npm run dev          # http://127.0.0.1:5173
   ```

3. 演示账号：`admin / Admin@123`（管理员，可见全部页面）、`analyst01 / Analyst@123`（分析师）、
   `dept_hn / Dept@123`（科室用户，用于证明数据隔离与管理页隐藏）。

## 二、采集脚本（自动）

```bash
cd backend
pip install playwright
python -m playwright install chromium
python ../deploy/capture_screenshots.py --base-url http://127.0.0.1:5173
```

脚本会依次登录并截图，输出到本目录（PNG，1920×1080）。

## 三、必须采集的截图清单（12 张）

| 编号 | 文件名 | 页面 | 路由 | 要点 |
| --- | --- | --- | --- | --- |
| S-01 | `01_login.png` | 登录页 | `/login` | 演示账号提示可见 |
| S-02 | `02_dashboard.png` | 管理驾驶舱 | `/dashboard` | 7 张 KPI 卡（全期口径）+ 收入趋势 + 科室排行 |
| S-03 | `03_outpatient.png` | 门诊分析 | `/outpatient` | 门诊人次趋势 + 号别构成 + 明细表 |
| S-04 | `04_inpatient.png` | 住院分析 | `/inpatient` | 出院人次趋势 + 床位使用率排行（下钻后） |
| S-05 | `05_revenue.png` | 收入分析 | `/revenue` | 收入趋势 + 药占比/耗占比 |
| S-06 | `06_disease_drg.png` | 病种分析 | `/disease` | DRG 入组率、CMI、消耗指数 |
| S-07 | `07_resource.png` | 资源效率 | `/resource` | 床位使用率、平均住院日、百元耗材 |
| S-08 | `08_report_center.png` | 报表中心 | `/report` | 多维查询结果 + 下钻按钮 |
| S-09 | `09_ai_chat.png` | 智能问数 | `/ai` | 问题「上月呼吸科床位使用率趋势如何」的数值+图表+解读 |
| S-10 | `10_admin_users.png` | 用户管理 | `/admin/users` | 用户列表与角色分配表单 |
| S-11 | `11_admin_tasks.png` | 任务管理 | `/admin/tasks` | 8 个任务状态 + 质量报告（评分 92.0） |
| S-12 | `12_dept_isolation.png` | 科室用户视角 | `/dashboard`（以 dept_hn 登录） | 数据范围 HN + 左侧菜单无「系统管理」组 |

## 四、人工核对要点

- KPI 数值应与《指标口径手册》第 5 章基线一致（门诊 9,000、床位使用率 88.89%、平均住院日 9.54 天等）；
- 数据源待补充指标（M04/M05/M27）应显示"待补充"标签而非 0；
- 科室用户截图必须体现「看不到报表中心与系统管理」。

## 五、纳入成果物的方式

截图采集完成后，在本目录保留 PNG，并在《成果物清单》"应用类 → 运营看板截图"一栏把状态从
"待采集"改为"已交付（12 张，路径 docs/screenshots/）"，同时把 2~3 张代表性截图嵌入《用户操作手册》第 15 章对应小节。
