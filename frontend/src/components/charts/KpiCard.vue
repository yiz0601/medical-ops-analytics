<template>
  <div class="kpi-card" :class="{ 'is-loading': loading }" :style="{ borderTopColor: resolvedColor }">
    <div class="kpi-title">
      <span>{{ data?.title || data?.metric_name || '指标' }}</span>
      <span v-if="data?.code" class="kpi-code">{{ data.code }}</span>
    </div>

    <div class="kpi-value">
      <span class="value">{{ displayValue }}</span>
      <span class="unit">{{ data?.unit || '' }}</span>
    </div>

    <div class="kpi-footer">
      <span v-if="momText" class="delta" :style="{ color: momColor }">
        {{ momArrow }} 环比 {{ momText }}
      </span>
      <span v-else class="delta muted">环比 —</span>
      <span v-if="data?.data_status === 'PENDING'" class="moa-tag warn">数据源待补充</span>
      <span v-else-if="data?.remark" class="remark">{{ data.remark }}</span>
    </div>
  </div>
</template>

<script setup>
/**
 * KPI 指标卡（阶段五 · 步骤 1-4）
 * 渲染指标数值、单位与同比/环比箭头方向；支持 data / loading / theme 三个统一 props。
 */
import { computed, watch } from 'vue'
import theme, { deltaColor } from '@/styles/theme'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  theme: { type: Object, default: () => theme }
})

const emit = defineEmits(['ready'])

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

const displayValue = computed(() => {
  const value = props.data?.metric_value ?? props.data?.value
  if (value === null || value === undefined) return '—'
  const unit = props.data?.unit || ''
  if (unit === '%') return numberFormatter.format(Number(value))
  return numberFormatter.format(Number(value))
})

const momValue = computed(() => {
  const mom = props.data?.mom
  return mom === null || mom === undefined ? null : Number(mom)
})

const momText = computed(() => (momValue.value === null ? '' : `${momValue.value > 0 ? '+' : ''}${momValue.value.toFixed(2)}%`))
const momColor = computed(() => deltaColor(momValue.value))
const momArrow = computed(() => {
  if (momValue.value === null) return ''
  if (momValue.value > 0) return '▲'
  if (momValue.value < 0) return '▼'
  return '—'
})
const resolvedColor = computed(() => props.theme?.primary || theme.primary)

// data 变化时通知外部（便于父组件做联动，例如高亮/记录）
watch(
  () => props.data,
  (value) => emit('ready', value),
  { deep: true }
)
</script>

<style scoped>
.kpi-card {
  background: #ffffff;
  border: 1px solid #e5e8ef;
  border-top: 3px solid #2f6fd0;
  border-radius: 8px;
  padding: 12px 14px;
  min-height: 96px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.kpi-card.is-loading {
  opacity: 0.6;
}

.kpi-title {
  font-size: 12px;
  color: #6b7785;
  display: flex;
  justify-content: space-between;
  gap: 6px;
}

.kpi-code {
  color: #98a2b3;
  font-size: 11px;
}

.kpi-value {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 6px 0 4px;
}

.kpi-value .value {
  font-size: 22px;
  font-weight: 700;
  color: #1f2733;
  font-variant-numeric: tabular-nums;
}

.kpi-value .unit {
  font-size: 12px;
  color: #6b7785;
}

.kpi-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-height: 18px;
}

.delta.muted,
.remark {
  color: #98a2b3;
}
</style>
