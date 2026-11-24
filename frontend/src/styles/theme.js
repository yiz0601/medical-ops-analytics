/**
 * 主题配色与图表默认样式（阶段五 · 步骤 1-5）
 * 集中导出主色、序列色板、文字与网格配色，所有图表组件默认引用。
 */
export const theme = {
  primary: '#2f6fd0',
  primaryLight: '#5b8fd8',
  success: '#2fa36b',
  warning: '#e6a23c',
  danger: '#d9534f',
  info: '#6b7785',
  // 序列色板（分类维度使用）
  colorPalette: [
    '#2f6fd0',
    '#2fa36b',
    '#e6a23c',
    '#8e79c4',
    '#d9534f',
    '#3aa8c1',
    '#b07d3a',
    '#7a8b99'
  ],
  bg: '#f5f7fb',
  cardBg: '#ffffff',
  border: '#e5e8ef',
  text: '#1f2733',
  textSecondary: '#6b7785',
  axisLine: '#dfe3ea',
  splitLine: '#eef1f6',
  // ECharts 通用基础配置
  baseOption: {
    textStyle: { fontFamily: 'Microsoft YaHei, PingFang SC, Arial, sans-serif' },
    grid: { left: 48, right: 24, top: 40, bottom: 32, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(31, 39, 51, 0.92)',
      borderWidth: 0,
      textStyle: { color: '#ffffff', fontSize: 12 }
    }
  }
}

/** 折线/柱状通用坐标轴配置 */
export const axisStyle = {
  axisLine: { lineStyle: { color: theme.axisLine } },
  axisTick: { show: false },
  axisLabel: { color: theme.textSecondary, fontSize: 11 },
  splitLine: { lineStyle: { color: theme.splitLine, type: 'dashed' } }
}

/** 指标卡状态色：正向/负向变化 */
export function deltaColor(delta) {
  if (delta === null || delta === undefined || Number.isNaN(Number(delta))) return theme.textSecondary
  return Number(delta) >= 0 ? theme.success : theme.danger
}

export default theme
