<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 热力图（阶段五 · 步骤 1-4）
 * data 形如 [{ x: '呼吸内科', y: '2025-04', value: 88.9 }]
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme from '@/styles/theme'

const props = defineProps({
  data: { type: Array, default: () => [] },
  title: { type: String, default: '' },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  theme: { type: Object, default: () => theme },
  emptyText: { type: String, default: '暂无数据' }
})

const hasData = computed(() => Array.isArray(props.data) && props.data.length > 0)

const axes = computed(() => {
  const xs = [...new Set(props.data.map((item) => String(item.x ?? '')))]
  const ys = [...new Set(props.data.map((item) => String(item.y ?? '')))]
  return { xs, ys }
})

const { chartRef, render } = useChart(() => {
  const { xs, ys } = axes.value
  const values = props.data.map((item) => Number(item.value ?? 0))
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const cells = props.data.map((item) => [xs.indexOf(String(item.x ?? '')), ys.indexOf(String(item.y ?? '')), Number(item.value ?? 0)])
  return {
    ...props.theme.baseOption,
    grid: { left: 8, right: 16, top: props.title ? 40 : 16, bottom: 48, containLabel: true },
    title: props.title ? { text: props.title, left: 0, textStyle: { fontSize: 13, color: '#1f2733' } } : undefined,
    tooltip: {
      ...props.theme.baseOption.tooltip,
      trigger: 'item',
      formatter: (params) => `${ys[params.data[1]]} · ${xs[params.data[0]]}<br/>${params.data[2]}${props.unit}`
    },
    xAxis: { type: 'category', data: xs, splitArea: { show: true }, axisLabel: { fontSize: 11, color: props.theme.textSecondary } },
    yAxis: { type: 'category', data: ys, splitArea: { show: true }, axisLabel: { fontSize: 11, color: props.theme.textSecondary } },
    visualMap: {
      min,
      max: max === min ? min + 1 : max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 80,
      textStyle: { fontSize: 10, color: props.theme.textSecondary },
      inRange: { color: ['#eaf1fb', '#9fc0ea', '#2f6fd0', '#1c4b91'] }
    },
    series: [
      {
        type: 'heatmap',
        data: cells,
        label: { show: true, fontSize: 10, color: '#1f2733' },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.2)' } }
      }
    ]
  }
})

watch(() => props.data, () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  min-height: 260px;
}

.chart-canvas {
  width: 100%;
  height: 260px;
}
</style>
