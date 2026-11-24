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
 * 资源效率看板（阶段五 · 步骤 2-6）
 * loadData(filters)  按筛选请求资源效率主题指标，刷新图表与明细表
 * handleDrill(dimValue) 处理图表点击下钻，加载下一层数据
 */
import { onMounted } from 'vue'
import ThemeBoard from '@/components/ThemeBoard.vue'
import { useThemeView } from '@/views/useThemeView'

const METRIC_LABELS = {
  M11: '床位使用率',
  M12: '平均住院日',
  M28: '医师人均门诊人次',
  M29: '床护比',
  M30: '百元收入耗材消耗'
}
const DEFAULT_METRICS = ['M11', 'M12', 'M30']

const board = useThemeView({
  theme: 'resource',
  defaultMetrics: DEFAULT_METRICS,
  metricLabels: METRIC_LABELS,
  mainMetric: 'M11'
})

const { loadData, handleDrill } = board

onMounted(() => loadData())
</script>
