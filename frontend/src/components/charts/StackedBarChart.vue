<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 堆叠柱状图（构成对比）—— 图表组件库第 7 类
 * 用法：<StackedBarChart :x="['HN','XH']" :series="[{name:'药品',data:[1,2]}]" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme, { axisStyle } from '@/styles/theme'

const props = defineProps({
  x: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  horizontal: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const hasData = computed(() => props.x.length > 0 && props.series.length > 0)

const { chartRef, render } = useChart(() => {
  if (!hasData.value) return null
  const categoryAxis = { type: 'category', data: props.x, ...axisStyle }
  const valueAxis = { type: 'value', name: props.unit, nameTextStyle: { color: '#98a2b3', fontSize: 11 }, ...axisStyle }
  return {
    ...props.theme.baseOption,
    color: props.theme.colorPalette,
    legend: { type: 'scroll', top: 0, right: 0, textStyle: { fontSize: 11, color: props.theme.textSecondary } },
    xAxis: props.horizontal ? valueAxis : categoryAxis,
    yAxis: props.horizontal ? categoryAxis : valueAxis,
    series: props.series.map((item) => ({
      name: item.name,
      type: 'bar',
      stack: 'total',
      barMaxWidth: 26,
      emphasis: { focus: 'series' },
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
