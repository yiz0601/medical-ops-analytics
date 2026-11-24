<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 占比饼图 / 环形图（阶段五 · 步骤 1-4）
 * data 形如 [{ name: '药品收入', value: 1234.5 }]
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme from '@/styles/theme'

const props = defineProps({
  data: { type: Array, default: () => [] },
  title: { type: String, default: '' },
  unit: { type: String, default: '' },
  donut: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
  theme: { type: Object, default: () => theme },
  emptyText: { type: String, default: '暂无数据' }
})

const hasData = computed(() => Array.isArray(props.data) && props.data.length > 0)

const { chartRef, render } = useChart(() => {
  const data = (props.data || []).map((item) => ({
    name: String(item.name ?? item.label ?? ''),
    value: item.value === null || item.value === undefined ? 0 : Number(item.value)
  }))
  return {
    color: props.theme.colorPalette,
    tooltip: { ...props.theme.baseOption.tooltip, trigger: 'item', formatter: `{b}<br/>{c}${props.unit}（{d}%）` },
    legend: { orient: 'vertical', right: 8, top: 'middle', textStyle: { color: props.theme.textSecondary, fontSize: 11 } },
    series: [
      {
        name: props.title || props.seriesName || '构成',
        type: 'pie',
        radius: props.donut ? ['42%', '66%'] : '64%',
        center: ['42%', '52%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#ffffff', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{d}%', fontSize: 11, color: props.theme.textSecondary },
        data
      }
    ]
  }
})

watch(() => props.data, () => render(), { deep: true })
</script>

<style scoped>
.chart-box {
  width: 100%;
  min-height: 220px;
}

.chart-canvas {
  width: 100%;
  height: 220px;
}
</style>
