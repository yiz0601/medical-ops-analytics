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
import { dashboardApi, themeMetrics } from '@/api/modules'
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
</script>

<style scoped>
.moa-btn.small {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
