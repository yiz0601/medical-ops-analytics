<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 面积图（支持多序列堆叠）—— 图表组件库第 6 类
 * 用法：<AreaChart :x="['2025-04','2025-05']" :series="[{name:'门诊',data:[1,2]}]" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme, { axisStyle } from '@/styles/theme'

const props = defineProps({
  x: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  stacked: { type: Boolean, default: true },
  areaOpacity: { type: Number, default: 0.28 },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const hasData = computed(() => props.x.length > 0 && props.series.length > 0)

const { chartRef, render } = useChart(() => {
  if (!hasData.value) return null
  return {
    ...props.theme.baseOption,
    color: props.theme.colorPalette,
    legend: { type: 'scroll', top: 0, right: 0, textStyle: { fontSize: 11, color: props.theme.textSecondary } },
    xAxis: { type: 'category', data: props.x, boundaryGap: false, ...axisStyle },
    yAxis: { type: 'value', name: props.unit, nameTextStyle: { color: '#98a2b3', fontSize: 11 }, ...axisStyle },
    series: props.series.map((item) => ({
      name: item.name,
      type: 'line',
      stack: props.stacked ? 'total' : undefined,
      smooth: true,
      showSymbol: false,
      areaStyle: { opacity: props.areaOpacity },
      lineStyle: { width: 1.6 },
      data: item.data.map((v) => (v === null || v === undefined ? null : Number(v)))
    }))
  }
})

watch(() => [props.x, props.series], () => render(), { deep: true })
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
