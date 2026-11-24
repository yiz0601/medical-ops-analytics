<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="value === null || value === undefined" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && value !== null && value !== undefined" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 仪表盘（单值达成率）—— 图表组件库第 9 类
 * 用法：<GaugeChart :value="88.89" name="床位使用率" unit="%" :max="100" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme from '@/styles/theme'

const props = defineProps({
  value: { type: Number, default: null },
  min: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  name: { type: String, default: '' },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  thresholds: { type: Array, default: () => [] },
  theme: { type: Object, default: () => theme }
})

const ratio = computed(() => {
  if (props.value === null || props.value === undefined) return 0
  const span = Number(props.max) - Number(props.min)
  if (!span) return 0
  return Math.min(1, Math.max(0, (Number(props.value) - Number(props.min)) / span))
})

const colorFor = computed(() => {
  for (const item of props.thresholds) {
    if (props.value !== null && props.value !== undefined && Number(props.value) <= Number(item.max)) {
      return item.color
    }
  }
  return props.theme.primary
})

const { chartRef, render } = useChart(() => {
  if (props.value === null || props.value === undefined) return null
  return {
    textStyle: { fontFamily: 'Microsoft YaHei, PingFang SC, Arial, sans-serif' },
    series: [
      {
        type: 'gauge',
        min: props.min,
        max: props.max,
        startAngle: 210,
        endAngle: -30,
        radius: '92%',
        center: ['50%', '58%'],
        progress: { show: true, width: 12, itemStyle: { color: colorFor.value } },
        axisLine: { lineStyle: { width: 12, color: [[1, '#eef1f6']] } },
        axisTick: { show: false },
        splitLine: { length: 8, lineStyle: { color: '#dfe3ea' } },
        axisLabel: { distance: -18, fontSize: 10, color: '#98a2b3' },
        pointer: { width: 4, itemStyle: { color: colorFor.value } },
        anchor: { show: true, size: 8, itemStyle: { color: colorFor.value } },
        title: { show: !!props.name, offsetCenter: [0, '72%'], fontSize: 12, color: props.theme.textSecondary },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '38%'],
          fontSize: 20,
          color: props.theme.text,
          formatter: (v) => `${Number(v).toFixed(2)}${props.unit}`
        },
        data: [{ value: Number(props.value), name: props.name }]
      }
    ]
  }
})

watch(() => [props.value, props.name], () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  height: 100%;
  min-height: 200px;
  position: relative;
}

.chart-canvas {
  width: 100%;
  height: 100%;
  min-height: 200px;
}
</style>
