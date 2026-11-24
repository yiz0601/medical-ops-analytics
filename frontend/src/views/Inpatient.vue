<template>
  <ThemeBoard
    :board="board"
    :metric-labels="METRIC_LABELS"
    :default-metrics="DEFAULT_METRICS"
    @reload="() => loadData()"
    @drill="handleDrill"
  />
</template>

<script setup>
/**
 * 住院看板（阶段五 · 步骤 2-3）
 * loadData(filters)  按筛选请求住院主题指标，刷新图表与明细表
 * handleDrill(dimValue) 处理图表点击下钻，加载下一层数据
 */
import { onMounted } from 'vue'
import ThemeBoard from '@/components/ThemeBoard.vue'
import { useThemeView } from '@/views/useThemeView'

const METRIC_LABELS = {
  M08: '出院人次',
  M09: '入院人次',
  M10: '实际占用床日',
  M11: '床位使用率',
  M12: '平均住院日',
  M13: '住院次均费用',
  M14: '手术占比',
  M15: '住院收入'
}
const DEFAULT_METRICS = ['M08', 'M11', 'M12']

const board = useThemeView({
  theme: 'inpatient',
  defaultMetrics: DEFAULT_METRICS,
  metricLabels: METRIC_LABELS,
  mainMetric: 'M08'
})

const { loadData, handleDrill } = board

onMounted(() => loadData())
</script>
