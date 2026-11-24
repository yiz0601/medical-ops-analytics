<template>
  <div>
    <!-- 筛选区 -->
    <div class="moa-card">
      <div class="moa-form-row">
        <label>粒度
          <select v-model="filters.granularity" class="moa-select" @change="loadOverview()">
            <option value="month">月度</option>
            <option value="period">全期</option>
          </select>
        </label>
        <label>开始 <input v-model="filters.startDate" type="date" class="moa-input" /></label>
        <label>结束 <input v-model="filters.endDate" type="date" class="moa-input" /></label>
        <button class="moa-btn" :disabled="state.loading" @click="loadOverview()">刷新</button>
        <span class="moa-tag" v-if="state.period">{{ state.period[0] }} ~ {{ state.period[1] }}</span>
        <span class="moa-tag">数据范围 {{ state.deptScope }}</span>
      </div>
      <div v-if="state.pending.length" class="pending-bar">
        数据源待补充指标：<span v-for="code in state.pending" :key="code" class="moa-tag warn">{{ code }}</span>
      </div>
    </div>

    <div v-if="state.error" class="moa-error">{{ state.error }}</div>

    <!-- KPI 卡片 -->
    <div class="moa-grid cols-4">
      <KpiCard v-for="kpi in state.kpis" :key="kpi.metric_code" :data="toCard(kpi)" :loading="state.loading" />
    </div>

    <!-- 趋势与排行 -->
    <div class="moa-grid cols-2">
      <div class="moa-card">
        <h3 class="moa-card-title">医疗收入趋势（M16）</h3>
        <TrendChart :data="state.trend" series-name="医疗收入" unit="元" :loading="state.loading" />
      </div>
      <div class="moa-card">
        <h3 class="moa-card-title">科室收入排行（点击查看科室看板）</h3>
        <RankBar :data="rankData" unit="元" :loading="state.loading" @drill="jumpToDept" />
      </div>
    </div>

    <!-- 明细 -->
    <div class="moa-card">
      <h3 class="moa-card-title">核心 KPI 明细</h3>
      <table class="moa-table">
        <thead>
          <tr>
            <th>指标</th>
            <th class="num">数值</th>
            <th>单位</th>
            <th class="num">环比</th>
            <th>数据状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in state.kpis" :key="row.metric_code">
            <td>{{ row.metric_code }} {{ row.metric_name }}</td>
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
      <p v-if="state.trend.length" class="hint">
        提示：单月口径受建仓窗口首尾效应影响（2025-06-30 集中出院 190 例），趋势解读请结合该说明。
      </p>
    </div>
  </div>
</template>

<script setup>
/**
 * 管理驾驶舱（阶段五 · 步骤 2-1）
 * loadOverview() 调用 GET /api/dashboard/overview，组合 KpiCard + TrendChart + RankBar 并联动日期筛选。
 */
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import KpiCard from '@/components/charts/KpiCard.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import RankBar from '@/components/charts/RankBar.vue'
import { dashboardApi } from '@/api/modules'
import { formatNumber } from '@/views/useThemeView'

const router = useRouter()

const filters = reactive({ granularity: 'month', startDate: '2025-04-01', endDate: '2025-06-30' })
const state = reactive({ loading: false, error: '', kpis: [], trend: [], deptRank: [], pending: [], period: [], deptScope: 'ALL' })

const rankData = computed(() =>
  state.deptRank.map((item) => ({ name: item.dept_name || item.dept_code, dept_code: item.dept_code, value: item.metric_value }))
)

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

/** 加载驾驶舱总览 */
async function loadOverview() {
  state.loading = true
  state.error = ''
  try {
    const data = await dashboardApi.overview({
      start_date: filters.startDate,
      end_date: filters.endDate,
      granularity: filters.granularity
    })
    state.kpis = data.kpis || []
    state.trend = data.trend || []
    state.deptRank = data.dept_rank || []
    state.pending = data.pending_metrics || []
    state.period = data.period || []
    state.deptScope = data.dept_scope || 'ALL'
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }
}

function jumpToDept(row) {
  if (row?.dept_code) {
    router.push({ path: '/revenue', query: { dept: row.dept_code } })
  }
}

onMounted(() => loadOverview())
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

.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #98a2b3;
}
</style>
