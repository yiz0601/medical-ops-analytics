<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 科室排行条形图（阶段五 · 步骤 1-4）
 * data 形如 [{ name: '呼吸内科', value: 1234.5, dept_code: 'HN' }]
 * 点击条形触发 drill 事件（供看板下钻）
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme, { axisStyle } from '@/styles/theme'

const props = defineProps({
  data: { type: Array, default: () => [] },
  title: { type: String, default: '' },
  unit: { type: String, default: '' },
  topN: { type: Number, default: 12 },
  drillable: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
  theme: { type: Object, default: () => theme },
  emptyText: { type: String, default: '暂无数据' }
})

const emit = defineEmits(['drill'])

const sorted = computed(() =>
  [...(props.data || [])]
    .map((item) => ({
      name: String(item.name ?? item.dept_name ?? ''),
      value: item.value === null || item.value === undefined ? 0 : Number(item.value),
      dept_code: item.dept_code || item.dim_value || ''
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, props.topN)
)

const hasData = computed(() => sorted.value.length > 0)

const { chartRef, render } = useChart(
  () => {
    const rows = sorted.value
    return {
      ...props.theme.baseOption,
      grid: { left: 8, right: 56, top: props.title ? 40 : 16, bottom: 8, containLabel: true },
      title: props.title ? { text: props.title, left: 0, textStyle: { fontSize: 13, color: '#1f2733' } } : undefined,
      tooltip: { ...props.theme.baseOption.tooltip, trigger: 'item', formatter: `{b}<br/>{c}${props.unit}` },
      xAxis: { type: 'value', ...axisStyle },
      yAxis: { type: 'category', data: rows.map((r) => r.name), ...axisStyle, splitLine: { show: false } },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => r.value),
          barMaxWidth: 18,
          itemStyle: { color: props.theme.primary, borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', fontSize: 11, color: props.theme.textSecondary }
        }
      ]
    }
  },
  {
    onReady(chart) {
      chart.on('click', (params) => {
        if (!props.drillable) return
        const row = sorted.value[params.dataIndex]
        if (row) emit('drill', row)
      })
    }
  }
)

watch(() => props.data, () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  min-height: 240px;
}

.chart-canvas {
  width: 100%;
  height: 240px;
}
</style>
