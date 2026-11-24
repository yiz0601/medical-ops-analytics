/**
 * 通用工具函数（对应工程目录结构中的 frontend/src/utils）
 * 数值格式化、维度名称映射、日期范围工具；多个视图与组合式函数共用，避免各页重复实现。
 */

/** 科室选项（与后端 dim_department / DEPT_CATALOG 一致） */
export const DEPT_OPTIONS = [
  { code: 'ALL', name: '全院' },
  { code: 'HN', name: '呼吸内科' },
  { code: 'HX', name: '消化内科' },
  { code: 'SJ', name: '神经内科' },
  { code: 'XH', name: '心血管内科' },
  { code: 'GK', name: '骨科' },
  { code: 'PW', name: '普外科' },
  { code: 'FC', name: '妇产科' },
  { code: 'EK', name: '儿科' },
  { code: 'JZ', name: '急诊科' },
  { code: 'ICU', name: '重症医学科' }
]

/** 科室编码 -> 中文名（未知编码原样返回） */
export function deptName(code) {
  const found = DEPT_OPTIONS.find((item) => item.code === code)
  return found ? found.name : code
}

/** 数值格式化：空值统一显示 —，其余按千分位保留至多 digits 位小数 */
export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

/** 百分比格式化：null -> —；否则保留 digits 位并补 % */
export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(digits)}%`
}

/** 变化率样式：>=0 用 success 色，<0 用 danger 色 */
export function deltaClass(delta) {
  if (delta === null || delta === undefined || Number.isNaN(Number(delta))) return 'delta-muted'
  return Number(delta) >= 0 ? 'delta-up' : 'delta-down'
}

/** 数据集统计期（与后端 Settings 默认统计期一致） */
export const STAT_PERIOD = { startDate: '2025-04-01', endDate: '2025-06-30' }

/** 生成 [开始日期, 结束日期] 参数数组；任一为空返回 null（由后端取默认统计期） */
export function buildDateRange(startDate, endDate) {
  if (!startDate || !endDate) return null
  return [startDate, endDate]
}

/** 把指标时序结果（series[]）拍平为明细表行，供表格与导出复用 */
export function flattenSeries(series = []) {
  const rows = []
  series.forEach((item) => {
    ;(item.points || []).forEach((point) => {
      rows.push({
        metric_code: item.metric_code,
        metric_name: item.metric_name,
        dim_value: item.dim_value,
        dept_name: deptName(item.dim_value),
        granularity: item.granularity,
        stat_date: point.stat_date,
        metric_value: point.metric_value,
        mom: point.mom,
        unit: item.unit,
        data_status: point.data_status
      })
    })
  })
  return rows
}

/** 组装逗号参数（空数组返回 undefined，避免发送空串） */
export function joinCodes(codes) {
  if (!Array.isArray(codes) || codes.length === 0) return undefined
  return codes.join(',')
}
