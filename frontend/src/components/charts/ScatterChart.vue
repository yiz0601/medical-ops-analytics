<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 散点图（相关性分析）—— 图表组件库第 8 类
 * 用法：<ScatterChart :points="[[x, y], ...]" x-name="门诊人次" y-name="收入（元）" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme, { axisStyle } from '@/styles/theme'

const props = defineProps({
  points: { type: Array, default: () => [] },
  xName: { type: String, default: 'X' },
  yName: { type: String, default: 'Y' },
  seriesName: { type: String, default: '科室' },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const hasData = computed(() => props.points.length > 0)

const { chartRef, render } = useChart(() => {
  if (!hasData.value) return null
  return {
    ...props.theme.baseOption,
    color: props.theme.colorPalette,
    tooltip: { ...props.theme.baseOption.tooltip, trigger: 'item' },
    xAxis: { type: 'value', name: props.xName, nameTextStyle: { color: '#98a2b3', fontSize: 11 }, ...axisStyle },
    yAxis: { type: 'value', name: props.yName, nameTextStyle: { color: '#98a2b3', fontSize: 11 }, ...axisStyle },
    series: [
      {
        name: props.seriesName,
        type: 'scatter',
        symbolSize: 14,
        data: props.points.map((p) => {
          if (Array.isArray(p)) return { value: [Number(p[0]), Number(p[1])] }
          return { value: [Number(p.x), Number(p.y)], name: p.name || '' }
        }),
        label: {
          show: props.points.length <= 14,
          position: 'right',
          fontSize: 10,
          color: props.theme.textSecondary,
          formatter: (params) => params.data?.name || ''
        }
      }
    ]
  }
})

watch(() => props.points, () => render(), { deep: true })
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
