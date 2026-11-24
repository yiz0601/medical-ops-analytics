/**
 * 主题看板通用逻辑（阶段五 · 步骤 2-1 ~ 2-6）
 * 五大主题看板共用：筛选条件、指标查询、下钻、图表数据派生、明细表。
 */
import { computed, reactive, ref } from 'vue'
import { themeMetrics } from '@/api/modules'
import { useUserStore } from '@/store/user'

export const DEPT_OPTIONS = [
  { code: 'ALL', name: '全院' },
  { code: 'HN', name: '呼吸内科' },
  { code: 'HX', name: '消化内科' },
  { code: 'SJ', name: '神经内科' },
  { code: 'XH', name: '心血管内科' },
  { code: 'GK', name: '骨科' },
  { code: 'PW', name: '普外科' },
  { code: 'FC', name: '妇产科' },
  { code: 'EK', name: '儿科' },
  { code: 'JZ', name: '急诊科' },
  { code: 'ICU', name: '重症医学科' }
]

export function useThemeView({ theme, defaultMetrics, metricLabels, mainMetric }) {
  const user = useUserStore()

  const filters = reactive({
    granularity: 'period',
    startDate: '2025-04-01',
    endDate: '2025-06-30',
    metrics: [...defaultMetrics],
    dept: user.deptCode || 'ALL'
  })

  const state = reactive({ loading: false, error: '', result: null, drillStack: [] })
  const lastLoaded = ref('')

  /** 按筛选条件请求主题指标（loadData(filters)） */
  async function loadData(overrides = {}) {
    Object.assign(filters, overrides)
    state.loading = true
    state.error = ''
    try {
      const params = {
        metrics: filters.metrics.join(','),
        granularity: filters.granularity,
        start_date: filters.startDate,
        end_date: filters.endDate
      }
      if (filters.dept && filters.dept !== 'ALL') {
        params.dims = filters.dept
      }
      const data = await themeMetrics(theme, params)
      state.result = data
      lastLoaded.value = new Date().toLocaleTimeString('zh-CN')
    } catch (error) {
      state.error = error.message || '加载失败'
      state.result = null
    } finally {
      state.loading = false
    }
  }

  /** 图表点击下钻：把维度值加入下钻栈并重新查询 */
  async function handleDrill(dimValue) {
    if (!dimValue) return
    const code = typeof dimValue === 'string' ? dimValue : dimValue.dept_code || dimValue.dim_value
    if (!code) return
    state.drillStack.push(code)
    await loadData({ dept: code, granularity: 'month' })
  }

  /** 返回上一级 */
  async function handleBack() {
    state.drillStack.pop()
    const parent = state.drillStack[state.drillStack.length - 1] || (user.deptCode || 'ALL')
    await loadData({ dept: parent, granularity: 'month' })
  }

  const primaryMetric = computed(() => mainMetric || filters.metrics[0])

  const seriesByMetric = computed(() => {
    const series = state.result?.series || []
    const grouped = {}
    series.forEach((item) => {
      if (!grouped[item.metric_code]) grouped[item.metric_code] = []
      grouped[item.metric_code].push(item)
    })
    return grouped
  })

  /** 主指标趋势（选定科室） */
  const trendData = computed(() => {
    const list = seriesByMetric.value[primaryMetric.value] || []
    const row = list.find((item) => item.dim_value === filters.dept) || list[0]
    return row?.points || []
  })

  /** 多指标趋势（用于堆叠对比） */
  const metricTrends = computed(() =>
    filters.metrics.map((code) => {
      const list = seriesByMetric.value[code] || []
      const row = list.find((item) => item.dim_value === filters.dept) || list[0]
      return { code, name: metricLabels?.[code] || code, points: row?.points || [], unit: row?.unit || '' }
    })
  )

  /** 科室排行（主指标最新一期） */
  const rankData = computed(() => {
    const list = seriesByMetric.value[primaryMetric.value] || []
    return list
      .filter((item) => item.dim_value !== 'ALL')
      .map((item) => {
        const points = item.points || []
        const latest = points[points.length - 1]
        return {
          name: deptName(item.dim_value),
          dept_code: item.dim_value,
          value: latest?.metric_value ?? null,
          unit: item.unit
        }
      })
      .filter((item) => item.value !== null)
  })

  /** 主指标科室构成（环形图） */
  const shareData = computed(() => rankData.value.map((item) => ({ name: item.name, value: item.value })))

  /** 明细表 */
  const tableRows = computed(() => {
    const rows = []
    Object.entries(seriesByMetric.value).forEach(([code, list]) => {
      list.forEach((item) => {
        item.points.forEach((point) => {
          rows.push({
            metric_code: code,
            metric_name: metricLabels?.[code] || point.metric_name || code,
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
    })
    return rows.slice(0, 200)
  })

  return {
    filters,
    state,
    lastLoaded,
    seriesByMetric,
    primaryMetric,
    trendData,
    metricTrends,
    rankData,
    shareData,
    tableRows,
    loadData,
    handleDrill,
    handleBack,
    metricLabels: metricLabels || {},
    deptOptions: DEPT_OPTIONS
  }
}

export function deptName(code) {
  const found = DEPT_OPTIONS.find((item) => item.code === code)
  return found ? found.name : code
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}
