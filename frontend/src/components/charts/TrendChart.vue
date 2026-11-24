<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 趋势折线图（阶段五 · 步骤 1-4）
 * data 形如 [{ stat_date: '2025-06-30', metric_value: 123.4 }] 或 { x: [], series: [] }
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme, { axisStyle } from '@/styles/theme'

const props = defineProps({
  data: { type: [Array, Object], default: () => [] },
  title: { type: String, default: '' },
  seriesName: { type: String, default: '指标值' },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  theme: { type: Object, default: () => theme }
})

const normalized = computed(() => {
  const raw = props.data
  if (Array.isArray(raw)) {
    const sorted = [...raw].sort((a, b) => String(a.stat_date).localeCompare(String(b.stat_date)))
    return {
      x: sorted.map((item) => String(item.stat_date || '')),
      series: sorted.map((item) => (item.metric_value === null || item.metric_value === undefined ? null : Number(item.metric_value)))
    }
  }
  return { x: raw?.x || [], series: (raw?.series || []).map((v) => (v === null ? null : Number(v))) }
})

const hasData = computed(() => normalized.value.x.length > 0)
const emptyText = computed(() => props.emptyText || '暂无数据')

const { chartRef, render } = useChart(() => {
  const { x, series } = normalized.value
  return {
    ...props.theme.baseOption,
    color: props.theme.colorPalette,
    title: props.title ? { text: props.title, left: 0, textStyle: { fontSize: 13, color: '#1f2733' } } : undefined,
    xAxis: { type: 'category', data: x, boundaryGap: false, ...axisStyle },
    yAxis: { type: 'value', name: props.unit, nameTextStyle: { color: '#98a2b3', fontSize: 11 }, ...axisStyle },
    series: [
      {
        name: props.seriesName,
        type: 'line',
        smooth: true,
        symbolSize: 6,
        data: series,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.08 },
        connectNulls: false
      }
    ]
  }
})

watch(() => props.data, () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  height: 100%;
  min-height: 220px;
  position: relative;
}

.chart-canvas {
  width: 100%;
  height: 100%;
  min-height: 220px;
}
</style>
