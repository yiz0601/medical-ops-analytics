<template>
  <div>
    <!-- 筛选区 -->
    <div class="moa-card">
      <div class="moa-form-row">
        <label>粒度
          <select v-model="board.filters.granularity" class="moa-select" @change="emit('reload')">
            <option value="period">全期</option>
            <option value="month">月度</option>
            <option value="day">日</option>
          </select>
        </label>
        <label>开始 <input v-model="board.filters.startDate" type="date" class="moa-input" /></label>
        <label>结束 <input v-model="board.filters.endDate" type="date" class="moa-input" /></label>
        <label>科室
          <select v-model="board.filters.dept" class="moa-select" @change="emit('reload')">
            <option v-for="item in board.deptOptions" :key="item.code" :value="item.code">{{ item.name }}</option>
          </select>
        </label>
        <button class="moa-btn" :disabled="board.state.loading" @click="emit('reload')">查询</button>
        <button v-if="board.state.drillStack.length" class="moa-btn ghost" @click="board.handleBack()">
          ← 返回上级
        </button>
        <span class="moa-tag">更新于 {{ board.lastLoaded.value || '—' }}</span>
      </div>
      <div class="moa-form-row">
        <label v-for="code in defaultMetrics" :key="code" class="metric-check">
          <input v-model="board.filters.metrics" type="checkbox" :value="code" @change="emit('reload')" />
          {{ metricLabels[code] || code }}
        </label>
      </div>
      <div v-if="board.state.drillStack.length" class="drill-path">
        当前下钻：{{ board.state.drillStack.join(' → ') }}
      </div>
    </div>

    <div v-if="board.state.error" class="moa-error">{{ board.state.error }}</div>

    <!-- 图表区 -->
    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">
          {{ metricLabels[board.primaryMetric.value] || '指标' }}趋势
          <span class="moa-tag">{{ granularityLabel }}</span>
        </h3>
        <TrendChart
          :data="board.trendData.value"
          :series-name="metricLabels[board.primaryMetric.value] || ''"
          :unit="board.trendData.value?.[0]?.unit || ''"
          :loading="board.state.loading"
        />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">科室排行（点击下钻）</h3>
        <RankBar
          :data="board.rankData.value"
          :unit="board.rankData.value?.[0]?.unit || ''"
          :loading="board.state.loading"
          @drill="emit('drill', $event)"
        />
      </div>
    </div>

    <!-- 面积趋势：多指标堆叠（门诊/住院/收入等主题共用） + 科室构成 -->
    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">多指标面积趋势（堆叠）</h3>
        <AreaChart :x="areaX" :series="areaSeries" :unit="board.trendData.value?.[0]?.unit || ''" :loading="board.state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">科室构成占比</h3>
        <PieChart :data="board.shareData.value" :loading="board.state.loading" />
      </div>
    </div>

    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">指标对比（含迷你趋势）</h3>
        <TrendTable :columns="compareColumns" :rows="compareTableRows" trend-label="主指标趋势" :loading="board.state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">维度明细统计</h3>
        <table class="moa-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>维度</th>
              <th class="num">最新值</th>
              <th>单位</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in compareRows" :key="row.code">
              <td>{{ metricLabels[row.code] || row.code }}</td>
              <td>{{ deptLabel(board.filters.dept) }}</td>
              <td class="num">{{ formatNumber(row.value) }}</td>
              <td>{{ row.unit || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 科室相关性散点（两个已选指标的科室最新值） -->
    <div class="moa-card">
      <h3 class="moa-card-title">科室相关性散点（前两项指标）</h3>
      <ScatterChart
        :points="scatterPoints"
        :x-name="scatterAxes.x"
        :y-name="scatterAxes.y"
        series-name="科室"
        :loading="board.state.loading"
      />
    </div>

    <!-- 明细表 -->
    <div class="moa-card">
      <h3 class="moa-card-title">
        指标明细
        <span class="moa-tag">{{ board.tableRows.value.length }} 行</span>
      </h3>
      <div v-if="!board.tableRows.value.length" class="moa-empty">暂无明细数据</div>
      <table v-else class="moa-table">
        <thead>
          <tr>
            <th>指标</th>
            <th>科室</th>
            <th>统计日期</th>
            <th class="num">指标值</th>
            <th>单位</th>
            <th class="num">环比</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in board.tableRows.value" :key="`${row.metric_code}-${row.dim_value}-${row.stat_date}-${index}`">
            <td>{{ row.metric_name }}</td>
            <td>{{ row.dept_name }}</td>
            <td>{{ row.stat_date }}</td>
            <td class="num">{{ formatNumber(row.metric_value) }}</td>
            <td>{{ row.unit }}</td>
            <td class="num">{{ row.mom === null || row.mom === undefined ? '—' : `${row.mom.toFixed(2)}%` }}</td>
            <td>
              <span :class="['moa-tag', row.data_status === 'PENDING' ? 'warn' : 'ok']">
                {{ row.data_status === 'PENDING' ? '待补充' : '正常' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
/**
 * 主题看板通用视图（阶段五 · 步骤 2-1 ~ 2-6）
 * 五大主题页共用：筛选、趋势、科室排行（点击下钻）、构成占比、指标对比与明细表。
 */
import { computed } from 'vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import RankBar from '@/components/charts/RankBar.vue'
import PieChart from '@/components/charts/PieChart.vue'
import AreaChart from '@/components/charts/AreaChart.vue'
import TrendTable from '@/components/charts/TrendTable.vue'
import ScatterChart from '@/components/charts/ScatterChart.vue'
import { deptName, formatNumber } from '@/views/useThemeView'

const props = defineProps({
  board: { type: Object, required: true },
  metricLabels: { type: Object, default: () => ({}) },
  defaultMetrics: { type: Array, default: () => [] }
})

const emit = defineEmits(['reload', 'drill'])

const granularityLabel = computed(() => {
  const map = { day: '日粒度', month: '月粒度', period: '全期' }
  return map[props.board.filters.granularity] || props.board.filters.granularity
})

const compareRows = computed(() =>
  props.board.metricTrends.value.map((item) => {
    const points = item.points || []
    const latest = points[points.length - 1]
    return { code: item.code, unit: item.unit, value: latest?.metric_value ?? null }
  })
)

/** 面积趋势：x 轴取主指标统计期，序列为勾选的各指标 */
const areaX = computed(() => (props.board.trendData.value || []).map((point) => point.stat_date))
const areaSeries = computed(() =>
  props.board.metricTrends.value
    .filter((item) => (item.points || []).length)
    .map((item) => ({ name: item.name, data: item.points.map((point) => point.metric_value) }))
)

/** 指标对比表（含主指标迷你趋势） */
const compareColumns = [
  { key: 'label', label: '指标', type: 'text' },
  { key: 'value', label: '最新值', digits: 2 },
  { key: 'unit', label: '单位', type: 'text' }
]

const compareTableRows = computed(() =>
  props.board.metricTrends.value.map((item) => {
    const latest = (item.points || [])[(item.points || []).length - 1]
    return {
      key: item.code,
      label: item.name,
      value: latest?.metric_value ?? null,
      unit: item.unit || '—',
      trend: (props.board.trendData.value || []).map((point) => point.metric_value)
    }
  })
)

/** 科室相关性散点：前两项已选指标的科室最新值 */
const scatterMetrics = computed(() => props.board.metricTrends.value.slice(0, 2))
const scatterAxes = computed(() => ({
  x: scatterMetrics.value[0]?.name || '指标一',
  y: scatterMetrics.value[1]?.name || '指标二'
}))

const scatterPoints = computed(() => {
  const [first, second] = scatterMetrics.value
  if (!first || !second) return []
  const latestByDept = (metric) => {
    const map = {}
    ;(props.board.seriesByMetric.value[metric.code] || []).forEach((item) => {
      const points = item.points || []
      const latest = points[points.length - 1]
      if (latest && latest.metric_value !== null && latest.metric_value !== undefined) {
        map[item.dim_value] = latest.metric_value
      }
    })
    return map
  }
  const firstMap = latestByDept(first)
  const secondMap = latestByDept(second)
  return Object.keys(firstMap)
    .filter((code) => code !== 'ALL' && secondMap[code] !== undefined)
    .map((code) => ({ x: firstMap[code], y: secondMap[code], name: deptName(code) }))
})

function deptLabel(code) {
  return deptName(code)
}
</script>

<style scoped>
.metric-check {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #3d4757;
}

.drill-path {
  font-size: 12px;
  color: #6b7785;
}
</style>
