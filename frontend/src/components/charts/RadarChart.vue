<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 雷达图（多指标能力画像）—— 图表组件库第 10 类
 * 用法：<RadarChart :indicators="[{name:'门诊量',max:100}]" :values="[80]" series-name="本科室" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme from '@/styles/theme'

const props = defineProps({
  indicators: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  seriesName: { type: String, default: '指标画像' },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const hasData = computed(() => props.indicators.length >= 3 && props.values.length > 0)

const { chartRef, render } = useChart(() => {
  if (!hasData.value) return null
  return {
    textStyle: { fontFamily: 'Microsoft YaHei, PingFang SC, Arial, sans-serif' },
    color: props.theme.colorPalette,
    tooltip: { ...props.theme.baseOption.tooltip, trigger: 'item' },
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: props.theme.textSecondary } },
    radar: {
      radius: '62%',
      center: ['50%', '56%'],
      indicator: props.indicators.map((item) => ({ name: item.name, max: Number(item.max) || 100 })),
      axisName: { color: props.theme.textSecondary, fontSize: 11 },
      splitLine: { lineStyle: { color: props.theme.splitLine } },
      splitArea: { areaStyle: { color: ['#ffffff', '#fafbfd'] } },
      axisLine: { lineStyle: { color: props.theme.splitLine } }
    },
    series: [
      {
        name: props.seriesName,
        type: 'radar',
        symbolSize: 5,
        areaStyle: { opacity: 0.25 },
        lineStyle: { width: 2 },
        data: [{ value: props.values.map((v) => Number(v ?? 0)), name: props.seriesName }]
      }
    ]
  }
})

watch(() => [props.indicators, props.values], () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  height: 100%;
  min-height: 240px;
  position: relative;
}

.chart-canvas {
  width: 100%;
  height: 100%;
  min-height: 240px;
}
</style>
