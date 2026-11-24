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
 * 收入看板（阶段五 · 步骤 2-4）
 * loadData(filters)  按筛选请求收入主题指标，刷新图表与明细表
 * handleDrill(dimValue) 处理图表点击下钻，加载下一层数据
 */
import { onMounted } from 'vue'
import ThemeBoard from '@/components/ThemeBoard.vue'
import { useThemeView } from '@/views/useThemeView'

const METRIC_LABELS = {
  M16: '医疗收入合计',
  M17: '药品收入',
  M18: '耗材收入',
  M19: '药占比',
  M20: '耗占比',
  M21: '检查检验占比',
  M22: '医疗服务性占比',
  M33: '收入增长率'
}
const DEFAULT_METRICS = ['M16', 'M19', 'M20']

const board = useThemeView({
  theme: 'revenue',
  defaultMetrics: DEFAULT_METRICS,
  metricLabels: METRIC_LABELS,
  mainMetric: 'M16'
})

const { loadData, handleDrill } = board

onMounted(() => loadData())
</script>
