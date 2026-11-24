<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">多维报表中心</h3>
      <div class="moa-form-row">
        <label>主题
          <select v-model="filters.theme" class="moa-select">
            <option value="revenue">收入分析</option>
            <option value="outpatient">门诊分析</option>
            <option value="inpatient">住院分析</option>
            <option value="disease">病种分析</option>
            <option value="resource">资源效率</option>
          </select>
        </label>
        <label>指标
          <select v-model="filters.metric" class="moa-select">
            <option v-for="item in metricOptions" :key="item.code" :value="item.code">{{ item.code }} {{ item.name }}</option>
          </select>
        </label>
        <label>维度
          <select v-model="filters.dept" class="moa-select">
            <option v-for="item in deptOptions" :key="item.code" :value="item.code">{{ item.name }}</option>
          </select>
        </label>
        <label>粒度
          <select v-model="filters.granularity" class="moa-select">
            <option value="month">月度</option>
            <option value="period">全期</option>
          </select>
        </label>
        <label>开始 <input v-model="filters.startDate" type="date" class="moa-input" /></label>
        <label>结束 <input v-model="filters.endDate" type="date" class="moa-input" /></label>
        <button class="moa-btn" :disabled="state.loading" @click="buildQuery()">查询</button>
        <button class="moa-btn ghost" :disabled="!state.rows.length" @click="handleExport()">导出 Excel</button>
      </div>
      <div v-if="state.drillPath.length" class="moa-form-row">
        <span class="moa-tag">下钻：{{ state.drillPath.join(' → ') }}</span>
        <button class="moa-btn ghost" @click="resetDrill()">清除下钻</button>
      </div>
    </div>

    <div v-if="state.error" class="moa-error">{{ state.error }}</div>

    <!-- 运营分析报告自动生成（大模型 / 模板双通道） -->
    <div class="moa-card">
      <h3 class="moa-card-title">
        运营分析报告自动生成
        <span class="moa-tag">{{ reportState.llmAvailable ? '大模型通道' : '模板通道（离线可用）' }}</span>
      </h3>
      <div class="moa-form-row">
        <label>报告类型
          <select v-model="reportFilters.reportType" class="moa-select">
            <option value="monthly">月报</option>
            <option value="weekly">周报</option>
          </select>
        </label>
        <label v-if="reportFilters.reportType === 'monthly'">期次
          <select v-model="reportFilters.month" class="moa-select">
            <option value="2025-04">2025-04</option>
            <option value="2025-05">2025-05</option>
            <option value="2025-06">2025-06</option>
          </select>
        </label>
        <label v-else>周次
          <input v-model="reportFilters.week" class="moa-input" placeholder="2025-W25" />
        </label>
        <button class="moa-btn" :disabled="reportState.loading" @click="generateReport()">生成报告</button>
        <button class="moa-btn ghost" :disabled="!reportState.report" @click="downloadReport()">下载 Markdown</button>
      </div>
      <div v-if="reportState.error" class="moa-error">{{ reportState.error }}</div>
      <div v-if="reportState.report" class="report-box">
        <h4 class="report-title">{{ reportState.report.title }}</h4>
        <p class="report-summary">{{ reportState.report.summary }}</p>
        <div v-for="chapter in reportState.report.chapters" :key="chapter.heading" class="report-chapter">
          <h5>{{ chapter.heading }}</h5>
          <p>{{ chapter.text }}</p>
          <div v-if="chapter.metrics && Object.keys(chapter.metrics).length" class="report-metrics">
            <span v-for="(value, key) in chapter.metrics" :key="key" class="moa-tag">{{ key }}：{{ formatNumber(value) }}</span>
          </div>
        </div>
        <div v-if="reportState.report.risk_items?.length" class="report-risk">
          <strong>风险提示</strong>
          <ul>
            <li v-for="(item, idx) in reportState.report.risk_items" :key="idx">{{ item }}</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="moa-card">
      <h3 class="moa-card-title">
        查询结果
        <span class="moa-tag">{{ state.rows.length }} 行</span>
      </h3>
      <div v-if="state.loading" class="moa-loading">查询中…</div>
      <div v-else-if="!state.rows.length" class="moa-empty">暂无数据，请调整筛选条件后查询</div>
      <table v-else class="moa-table">
        <thead>
          <tr>
            <th>指标</th>
            <th>科室</th>
            <th>统计日期</th>
            <th class="num">指标值</th>
            <th>单位</th>
            <th class="num">环比</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in state.rows" :key="`${row.dim_value}-${row.stat_date}-${index}`">
            <td>{{ row.metric_name }}</td>
            <td>{{ row.dept_name }}</td>
            <td>{{ row.stat_date }}</td>
            <td class="num">{{ formatNumber(row.metric_value) }}</td>
            <td>{{ row.unit }}</td>
            <td class="num">{{ row.mom === null || row.mom === undefined ? '—' : `${row.mom.toFixed(2)}%` }}</td>
            <td>
              <button class="moa-btn ghost small" :disabled="row.dim_value === 'ALL'" @click="handleDrill(row)">
                下钻
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
/**
 * 多维报表中心（阶段五 · 步骤 3-1）
 * buildQuery()   组装维度组合、指标、日期与同比/环比参数发起查询
 * handleDrill()  报表图表下钻至下一维度层级（科室 → 月度明细）
 * handleExport() 调用导出接口触发 Excel 下载
 */
import { computed, onMounted, reactive } from 'vue'
import { aiApi, dashboardApi, themeMetrics } from '@/api/modules'
import { DEPT_OPTIONS, deptName, formatNumber } from '@/views/useThemeView'

const METRIC_OPTIONS = {
  revenue: [
    { code: 'M16', name: '医疗收入合计' },
    { code: 'M17', name: '药品收入' },
    { code: 'M19', name: '药占比' },
    { code: 'M20', name: '耗占比' }
  ],
  outpatient: [
    { code: 'M01', name: '门诊人次' },
    { code: 'M03', name: '门诊次均费用' },
    { code: 'M07', name: '门诊收入' }
  ],
  inpatient: [
    { code: 'M08', name: '出院人次' },
    { code: 'M11', name: '床位使用率' },
    { code: 'M12', name: '平均住院日' }
  ],
  disease: [
    { code: 'M23', name: 'DRG 入组率' },
    { code: 'M24', name: 'CMI' },
    { code: 'M25', name: '费用消耗指数' }
  ],
  resource: [
    { code: 'M11', name: '床位使用率' },
    { code: 'M28', name: '医师人均门诊人次' },
    { code: 'M30', name: '百元收入耗材消耗' }
  ]
}

const filters = reactive({
  theme: 'revenue',
  metric: 'M16',
  dept: 'ALL',
  granularity: 'period',
  startDate: '2025-04-01',
  endDate: '2025-06-30'
})

const state = reactive({ loading: false, error: '', rows: [], drillPath: [] })

const deptOptions = DEPT_OPTIONS
const metricOptions = computed(() => METRIC_OPTIONS[filters.theme] || [])

/** 组装参数并发起查询 */
async function buildQuery() {
  state.loading = true
  state.error = ''
  try {
    const params = {
      metrics: filters.metric,
      granularity: filters.granularity,
      start_date: filters.startDate,
      end_date: filters.endDate
    }
    if (filters.dept !== 'ALL') params.dims = filters.dept
    const data = await themeMetrics(filters.theme, params)
    const rows = []
    ;(data.series || []).forEach((item) => {
      ;(item.points || []).forEach((point) => {
        rows.push({
          metric_code: item.metric_code,
          metric_name: item.metric_name,
          dept_name: deptName(item.dim_value),
          dim_value: item.dim_value,
          stat_date: point.stat_date,
          metric_value: point.metric_value,
          mom: point.mom,
          unit: item.unit,
          data_status: point.data_status
        })
      })
    })
    state.rows = rows
  } catch (error) {
    state.error = error.message || '查询失败'
    state.rows = []
  } finally {
    state.loading = false
  }
}

/** 下钻：切换为月度并锁定该科室 */
async function handleDrill(row) {
  if (!row || !row.dim_value || row.dim_value === 'ALL') return
  state.drillPath.push(row.dept_name)
  filters.dept = row.dim_value
  filters.granularity = 'month'
  await buildQuery()
}

function resetDrill() {
  state.drillPath = []
  filters.dept = 'ALL'
  filters.granularity = 'period'
  buildQuery()
}

/** 导出 Excel（blob 下载） */
async function handleExport() {
  state.error = ''
  try {
    const response = await dashboardApi.exportFile({
      metric: filters.metric,
      dims: filters.dept === 'ALL' ? undefined : filters.dept,
      start_date: filters.startDate,
      end_date: filters.endDate,
      granularity: filters.granularity,
      format: 'xlsx'
    })
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    })
    const filename = `指标导出_${filters.metric}_${Date.now()}.xlsx`
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    state.error = `导出失败：${error.message}`
  }
}

onMounted(() => buildQuery())

// ---------------------------------------------------------------- 报告自动生成
const reportFilters = reactive({ reportType: 'monthly', month: '2025-06', week: '2025-W25' })
const reportState = reactive({ loading: false, error: '', report: null, llmAvailable: false })

/** 调用 POST /api/llm/report 生成周报 / 月报（无密钥时走模板通道） */
async function generateReport() {
  reportState.loading = true
  reportState.error = ''
  try {
    const payload = { report_type: reportFilters.reportType }
    if (reportFilters.reportType === 'monthly') payload.month = reportFilters.month
    else payload.week = reportFilters.week
    const data = await aiApi.report(payload)
    reportState.report = data
    reportState.llmAvailable = !!data.llm_available
  } catch (error) {
    reportState.error = error.message || '报告生成失败'
    reportState.report = null
  } finally {
    reportState.loading = false
  }
}

/** 把生成的报告导出为 Markdown 文件（浏览器端下载） */
function downloadReport() {
  const report = reportState.report
  if (!report) return
  const lines = [`# ${report.title}`, '', report.summary || '', '']
  ;(report.chapters || []).forEach((chapter) => {
    lines.push(`## ${chapter.heading}`, '', chapter.text || '', '')
    const entries = Object.entries(chapter.metrics || {})
    if (entries.length) {
      lines.push('| 指标 | 数值 |', '| --- | --- |')
      entries.forEach(([key, value]) => lines.push(`| ${key} | ${formatNumber(value)} |`))
      lines.push('')
    }
  })
  if (report.risk_items?.length) {
    lines.push('## 风险提示', '')
    report.risk_items.forEach((item) => lines.push(`- ${item}`))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${report.title || '运营分析报告'}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
</script>

<style scoped>
.report-box {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid #e5e8ef;
  border-radius: 10px;
  background: #fbfcfe;
}

.report-title {
  margin: 0 0 8px;
  font-size: 16px;
  color: #1f2733;
}

.report-summary {
  margin: 0 0 12px;
  font-size: 13px;
  color: #2f6fd0;
  line-height: 1.7;
}

.report-chapter h5 {
  margin: 12px 0 4px;
  font-size: 13px;
  color: #1f2733;
}

.report-chapter p {
  margin: 0 0 6px;
  font-size: 12.5px;
  color: #4a5566;
  line-height: 1.75;
}

.report-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.report-risk {
  margin-top: 12px;
  font-size: 12.5px;
  color: #b7791f;
}

.report-risk ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.7;
}

.moa-btn.small {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
