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
 * 病种看板（阶段五 · 步骤 2-5）
 * loadData(filters)  按筛选请求病种（DRG/DIP）主题指标，刷新图表与明细表
 * handleDrill(dimValue) 处理图表点击下钻，加载下一层数据
 *
 * 说明：DRG 分组为模拟分组（dim_disease），M27 低风险组死亡率因缺死亡标识显示"待补充"。
 */
import { onMounted } from 'vue'
import ThemeBoard from '@/components/ThemeBoard.vue'
import { useThemeView } from '@/views/useThemeView'

const METRIC_LABELS = {
  M23: 'DRG 入组率',
  M24: 'CMI',
  M25: '费用消耗指数',
  M26: '时间消耗指数',
  M27: '低风险组死亡率'
}
const DEFAULT_METRICS = ['M23', 'M24', 'M25']

const board = useThemeView({
  theme: 'disease',
  defaultMetrics: DEFAULT_METRICS,
  metricLabels: METRIC_LABELS,
  mainMetric: 'M24'
})

const { loadData, handleDrill } = board

onMounted(() => loadData())
</script>
