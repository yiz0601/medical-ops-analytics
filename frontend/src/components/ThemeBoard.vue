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

    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">科室构成占比</h3>
        <PieChart :data="board.shareData.value" :loading="board.state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">指标对比</h3>
        <div v-if="board.state.loading" class="moa-loading">加载中…</div>
        <table v-else class="moa-table">
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
