<template>
  <div class="chart-box">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!hasData" class="moa-empty">{{ emptyText }}</div>
    <div v-show="!loading && hasData" ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<script setup>
/**
 * 漏斗图（转化 / 构成逐级）—— 图表组件库第 11 类
 * 用法：<FunnelChart :items="[{name:'医疗收入',value:44260283.8}]" />
 */
import { computed, watch } from 'vue'
import { useChart } from './useChart'
import theme from '@/styles/theme'

const props = defineProps({
  items: { type: Array, default: () => [] },
  unit: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const hasData = computed(() => props.items.length > 0)

const { chartRef, render } = useChart(() => {
  if (!hasData.value) return null
  const sorted = [...props.items].sort((a, b) => Number(b.value) - Number(a.value))
  return {
    textStyle: { fontFamily: 'Microsoft YaHei, PingFang SC, Arial, sans-serif' },
    color: props.theme.colorPalette,
    tooltip: {
      ...props.theme.baseOption.tooltip,
      trigger: 'item',
      formatter: (params) =>
        `${params.name}<br/>${Number(params.value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}${props.unit}`
    },
    legend: { top: 0, right: 0, textStyle: { fontSize: 11, color: props.theme.textSecondary } },
    series: [
      {
        type: 'funnel',
        left: '8%',
        right: '8%',
        top: 32,
        bottom: 12,
        minSize: '24%',
        sort: 'descending',
        gap: 2,
        label: { position: 'inside', fontSize: 11, color: '#ffffff' },
        data: sorted.map((item) => ({ name: item.name, value: Number(item.value) }))
      }
    ]
  }
})

watch(() => props.items, () => render(), { deep: true })
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
