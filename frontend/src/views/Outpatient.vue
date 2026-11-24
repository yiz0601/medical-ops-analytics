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
 * 门诊看板（阶段五 · 步骤 2-2）
 * loadData(filters)  按筛选请求门诊主题指标，刷新图表与明细表
 * handleDrill(dimValue) 处理图表点击下钻，加载下一层数据
 */
import { onMounted } from 'vue'
import ThemeBoard from '@/components/ThemeBoard.vue'
import { useThemeView } from '@/views/useThemeView'

const METRIC_LABELS = {
  M01: '门诊人次',
  M02: '号别结构占比',
  M03: '门诊次均费用',
  M06: '门急诊人次',
  M07: '门诊收入'
}
const DEFAULT_METRICS = ['M01', 'M03', 'M07']

const board = useThemeView({
  theme: 'outpatient',
  defaultMetrics: DEFAULT_METRICS,
  metricLabels: METRIC_LABELS,
  mainMetric: 'M01'
})

const { loadData, handleDrill } = board

onMounted(() => loadData())
</script>
