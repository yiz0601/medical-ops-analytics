<template>
  <div>
    <!-- 筛选区 -->
    <div class="moa-card">
      <div class="moa-form-row">
        <label>科室
          <select v-model="filters.dept" class="moa-select" :disabled="locked" @change="loadBoard()">
            <option v-for="item in deptOptions" :key="item.code" :value="item.code">{{ item.name }}</option>
          </select>
        </label>
        <label>粒度
          <select v-model="filters.granularity" class="moa-select" @change="loadBoard()">
            <option value="month">月度</option>
            <option value="period">全期</option>
          </select>
        </label>
        <label>开始 <input v-model="filters.startDate" type="date" class="moa-input" /></label>
        <label>结束 <input v-model="filters.endDate" type="date" class="moa-input" /></label>
        <button class="moa-btn" :disabled="state.loading" @click="loadBoard()">刷新</button>
        <span v-if="state.period.length" class="moa-tag">{{ state.period[0] }} ~ {{ state.period[1] }}</span>
        <span class="moa-tag">{{ state.deptName }}（{{ state.deptCode }}）</span>
      </div>
      <div v-if="state.pending.length" class="pending-bar">
        数据源待补充指标：<span v-for="code in state.pending" :key="code" class="moa-tag warn">{{ code }}</span>
      </div>
    </div>

    <div v-if="state.error" class="moa-error">{{ state.error }}</div>

    <!-- 科室核心指标卡 -->
    <div class="moa-grid cols-4">
      <KpiCard v-for="kpi in state.kpis" :key="kpi.metric_code" :data="toCard(kpi)" :loading="state.loading" />
    </div>

    <!-- 床位使用率仪表盘 + 能力画像雷达 + 横向名次 -->
    <div class="moa-grid cols-3">
      <div class="moa-card">
        <h3 class="moa-card-title">床位使用率（M11）</h3>
        <GaugeChart
          :value="metricValue('M11')"
          name="床位使用率"
          unit="%"
          :max="120"
          :thresholds="[{ max: 100, color: '#2fa36b' }, { max: 999, color: '#e6a23c' }]"
          :loading="state.loading"
        />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">指标画像（相对全院归一）</h3>
        <RadarChart :indicators="radarIndicators" :values="radarValues" series-name="本科室" :loading="state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">科室收入横向名次（M16）</h3>
        <div class="rank-box">
          <div class="rank-num">
            <strong>{{ state.rank?.rank ?? '—' }}</strong><span> / {{ state.rank?.total_depts ?? '—' }}</span>
          </div>
          <p class="rank-desc">
            本期收入 {{ formatNumber(state.rank?.metric_value) }} {{ state.rank?.unit || '元' }}，
            在全院 {{ state.rank?.total_depts ?? 0 }} 个临床科室中位列第 {{ state.rank?.rank ?? '—' }}。
          </p>
          <div class="staff-box">
            <span class="moa-tag">人力台账 {{ state.staff.stat_date || '未就绪' }}</span>
            <span class="moa-tag">医师 {{ state.staff.doctor_cnt }}</span>
            <span class="moa-tag">护士 {{ state.staff.nurse_cnt }}</span>
            <span class="moa-tag">卫技 {{ state.staff.staff_total }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 趋势：床位使用率面积图 + 平均住院日折线 -->
    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">床位使用率趋势（M11，面积图）</h3>
        <AreaChart :x="areaX" :series="areaSeries" unit="%" :loading="state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">平均住院日趋势（M12）</h3>
        <TrendChart :data="trendOf('M12')" series-name="平均住院日" unit="天" :loading="state.loading" />
      </div>
    </div>

    <!-- 收入构成：堆叠柱 + 漏斗 -->
    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">费别收入构成（堆叠柱）</h3>
        <StackedBarChart :x="compositionX" :series="compositionSeries" unit="元" :loading="state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">收入结构（漏斗）</h3>
        <FunnelChart :items="funnelItems" unit="元" :loading="state.loading" />
      </div>
    </div>

    <!-- 科室月度明细（含迷你趋势） -->
    <div class="moa-card">
      <h3 class="moa-card-title">科室月度指标明细（含迷你趋势）</h3>
      <TrendTable :columns="tableColumns" :rows="tableRows" trend-label="门诊人次趋势" :loading="state.loading" />
    </div>
  </div>
</template>

<script setup>
/**
 * 科室运营看板（第三套看板）
 * 调用 GET /api/dashboard/dept，组合 KpiCard / GaugeChart / RadarChart / AreaChart /
 * TrendChart / StackedBarChart / FunnelChart / TrendTable 八类组件，
 * 覆盖单科室全指标、床位与住院日趋势、费别构成、横向名次与人事系统人力快照。
 */
import { computed, onMounted, reactive } from 'vue'
import KpiCard from '@/components/charts/KpiCard.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import AreaChart from '@/components/charts/AreaChart.vue'
import StackedBarChart from '@/components/charts/StackedBarChart.vue'
import GaugeChart from '@/components/charts/GaugeChart.vue'
import RadarChart from '@/components/charts/RadarChart.vue'
import FunnelChart from '@/components/charts/FunnelChart.vue'
import TrendTable from '@/components/charts/TrendTable.vue'
import { dashboardApi } from '@/api/modules'
import { useUserStore } from '@/store/user'
import { DEPT_OPTIONS, formatNumber, deptName } from '@/views/useThemeView'

const user = useUserStore()
const locked = computed(() => user.role === 'DEPT_USER')

const filters = reactive({
  dept: user.deptCode || DEPT_OPTIONS[0]?.code || 'HN',
  granularity: 'period',
  startDate: '2025-04-01',
  endDate: '2025-06-30'
})

const state = reactive({
  loading: false,
  error: '',
  deptCode: filters.dept,
  deptName: deptName(filters.dept),
  period: [],
  kpis: [],
  trends: [],
  composition: [],
  rank: null,
  staff: { doctor_cnt: 0, nurse_cnt: 0, staff_total: 0, stat_date: null },
  pending: []
})

const deptOptions = DEPT_OPTIONS

function toCard(kpi) {
  return {
    code: kpi.metric_code,
    title: kpi.metric_name,
    metric_value: kpi.metric_value,
    unit: kpi.unit,
    mom: kpi.mom,
    data_status: kpi.data_status
  }
}

function metricValue(code) {
  const row = state.kpis.find((item) => item.metric_code === code)
  return row?.metric_value ?? null
}

function trendOf(code) {
  const item = state.trends.find((t) => t.metric_code === code)
  return item?.points || []
}

const areaX = computed(() => trendOf('M11').map((p) => p.stat_date))
const areaSeries = computed(() => [{ name: '床位使用率', data: trendOf('M11').map((p) => p.metric_value) }])

/** 指标画像：把科室核心指标按阈值归一（0~100），用于雷达对比 */
const RADAR_CONFIG = [
  { code: 'M01', name: '门诊人次', max: 1200 },
  { code: 'M08', name: '出院人次', max: 200 },
  { code: 'M11', name: '床位使用率', max: 120 },
  { code: 'M12', name: '平均住院日(反向)', max: 14, reverse: true },
  { code: 'M16', name: '医疗收入(万)', max: 600, divisor: 10000 },
  { code: 'M28', name: '医师人均门诊', max: 120 }
]

const radarIndicators = computed(() => RADAR_CONFIG.map((item) => ({ name: item.name, max: 100 })))
const radarValues = computed(() =>
  RADAR_CONFIG.map((item) => {
    const value = metricValue(item.code)
    if (value === null || value === undefined) return 0
    const scaled = item.divisor ? Number(value) / item.divisor : Number(value)
    const ratio = Math.min(1, Math.max(0, scaled / item.max))
    return Number(((item.reverse ? 1 - ratio : ratio) * 100).toFixed(2))
  })
)

/** 费别构成：堆叠柱（单科室的各类收入） */
const COMPOSITION_LABELS = { M17: '药品收入', M18: '耗材收入', M21: '检查检验占比', M22: '医疗服务性占比' }
const compositionX = computed(() => state.composition.map((item) => COMPOSITION_LABELS[item.metric_code] || item.metric_code))
const compositionSeries = computed(() => [
  { name: state.deptName, data: state.composition.map((item) => item.metric_value) }
])
const funnelItems = computed(() =>
  state.composition
    .filter((item) => ['M17', 'M18'].includes(item.metric_code))
    .map((item) => ({ name: COMPOSITION_LABELS[item.metric_code] || item.metric_code, value: item.metric_value }))
)

/** 月度明细表（含门诊人次迷你趋势） */
const tableColumns = [
  { key: 'stat_date', label: '统计期', type: 'text' },
  { key: 'm11', label: '床位使用率', unit: '%', digits: 2 },
  { key: 'm12', label: '平均住院日', unit: '天', digits: 2 },
  { key: 'm16', label: '医疗收入', unit: '元', digits: 2 }
]

const tableRows = computed(() => {
  const dates = trendOf('M16').map((p) => p.stat_date)
  const valueAt = (code, idx) => trendOf(code)[idx]?.metric_value ?? null
  return dates.map((statDate, idx) => ({
    key: `${statDate}-${idx}`,
    stat_date: statDate,
    m11: valueAt('M11', idx),
    m12: valueAt('M12', idx),
    m16: valueAt('M16', idx),
    trend: trendOf('M01').map((p) => p.metric_value)
  }))
})

/** 加载科室看板 */
async function loadBoard() {
  state.loading = true
  state.error = ''
  try {
    const data = await dashboardApi.dept({
      dept: filters.dept,
      start_date: filters.startDate,
      end_date: filters.endDate,
      granularity: filters.granularity
    })
    state.deptCode = data.dept_code
    state.deptName = data.dept_name || deptName(data.dept_code)
    state.period = data.period || []
    state.kpis = data.kpis || []
    state.trends = data.trends || []
    state.composition = data.composition || []
    state.rank = data.rank || null
    state.staff = data.staff || state.staff
    state.pending = data.pending_metrics || []
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }
}

onMounted(() => loadBoard())
</script>

<style scoped>
.pending-bar {
  font-size: 12px;
  color: #6b7785;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.rank-box {
  padding: 6px 2px;
}

.rank-num strong {
  font-size: 34px;
  color: #2f6fd0;
}

.rank-num span {
  font-size: 14px;
  color: #98a2b3;
}

.rank-desc {
  margin: 8px 0 12px;
  font-size: 12px;
  color: #6b7785;
  line-height: 1.6;
}

.staff-box {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
