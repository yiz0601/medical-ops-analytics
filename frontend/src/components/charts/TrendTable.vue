<template>
  <div class="trend-table">
    <div v-if="loading" class="moa-loading">加载中…</div>
    <div v-else-if="!rows.length" class="moa-empty">{{ emptyText }}</div>
    <table v-else class="moa-table">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key" :style="{ textAlign: col.align || 'left' }">{{ col.label }}</th>
          <th class="trend-head">{{ trendLabel }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, idx) in rows" :key="row.key || idx">
          <td v-for="col in columns" :key="col.key" :style="{ textAlign: col.align || 'left' }">
            {{ formatCell(row, col) }}
          </td>
          <td class="trend-cell">
            <svg class="spark" viewBox="0 0 80 22" preserveAspectRatio="none" role="img" :aria-label="`${trendLabel}迷你趋势`">
              <polyline
                v-if="sparkPoints(row).length > 1"
                :points="sparkPoints(row)"
                fill="none"
                :stroke="sparkColor(row)"
                stroke-width="1.6"
                stroke-linejoin="round"
                stroke-linecap="round"
              />
              <circle
                v-if="sparkPoints(row).length"
                :cx="lastPoint(row).x"
                :cy="lastPoint(row).y"
                r="2"
                :fill="sparkColor(row)"
              />
            </svg>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
/**
 * 明细表（含迷你趋势 sparkline）—— 图表组件库第 12 类
 * 用法：<TrendTable :columns="[{key:'value',label:'最新值'}]" :rows="[{label:'HN',values:{value:900},trend:[1,2,3]}]" />
 */
import { computed } from 'vue'
import { formatNumber } from '@/utils/format'
import theme from '@/styles/theme'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  trendKey: { type: String, default: 'trend' },
  trendLabel: { type: String, default: '迷你趋势' },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  theme: { type: Object, default: () => theme }
})

const trendValues = (row) => (Array.isArray(row?.[props.trendKey]) ? row[props.trendKey] : [])

function sparkPoints(row) {
  const values = trendValues(row).map((v) => (v === null || v === undefined ? null : Number(v)))
  const valid = values.filter((v) => Number.isFinite(v))
  if (valid.length < 2) return ''
  const min = Math.min(...valid)
  const max = Math.max(...valid)
  const span = max - min || 1
  const step = 80 / (values.length - 1)
  return values
    .map((value, idx) => {
      if (!Number.isFinite(value)) return null
      const x = (idx * step).toFixed(2)
      const y = (20 - ((value - min) / span) * 18).toFixed(2)
      return `${x},${y}`
    })
    .filter(Boolean)
    .join(' ')
}

function lastPoint(row) {
  const points = sparkPoints(row)
  if (!points) return { x: 0, y: 0 }
  const last = points.split(' ').pop().split(',')
  return { x: Number(last[0]), y: Number(last[1]) }
}

function sparkColor(row) {
  const values = trendValues(row).filter((v) => v !== null && v !== undefined).map(Number)
  if (values.length < 2) return props.theme.textSecondary
  return values[values.length - 1] >= values[0] ? props.theme.success : props.theme.danger
}

function formatCell(row, col) {
  const raw = row?.values?.[col.key] ?? row?.[col.key]
  if (raw === null || raw === undefined || raw === '') return '-'
  if (col.type === 'text') return String(raw)
  const text = formatNumber(raw, col.digits)
  return col.unit ? `${text}${col.unit}` : text
}

const hasTrend = computed(() => props.rows.some((row) => trendValues(row).length > 1))
</script>

<style scoped>
.trend-table {
  width: 100%;
}

.trend-head,
.trend-cell {
  width: 96px;
  text-align: center;
}

.spark {
  width: 80px;
  height: 22px;
  vertical-align: middle;
}

.moa-empty,
.moa-loading {
  padding: 18px;
  text-align: center;
  color: #98a2b3;
  font-size: 13px;
}
</style>
