/**
 * ECharts 按需引入与通用渲染逻辑（阶段五 · 步骤 1-4）
 * - 只注册用到的图表与组件，控制打包体积
 * - 统一封装实例创建、数据更新（setOption）、容器尺寸自适应（ResizeObserver）与销毁
 * - 支持传入 onReady 回调绑定交互事件（如点击下钻）
 */
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  VisualMapComponent,
  MarkLineComponent,
  CanvasRenderer
])

/**
 * 图表渲染 composable
 * @param {() => object} buildOption 返回 ECharts option 的函数
 * @param {{ onReady?: (chart: object) => void }} options 初始化完成后的回调
 */
export function useChart(buildOption, options = {}) {
  const chartRef = ref(null)
  const chartInstance = shallowRef(null)
  let observer = null

  const render = () => {
    if (!chartRef.value) return
    if (!chartInstance.value) {
      chartInstance.value = echarts.init(chartRef.value, null, { renderer: 'canvas' })
      if (typeof options.onReady === 'function') {
        options.onReady(chartInstance.value)
      }
    }
    const option = buildOption()
    if (option) {
      chartInstance.value.setOption(option, true)
    }
  }

  const resize = () => {
    if (chartInstance.value) chartInstance.value.resize()
  }

  onMounted(() => {
    render()
    if (chartRef.value && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => resize())
      observer.observe(chartRef.value)
    }
    window.addEventListener('resize', resize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    if (observer) {
      observer.disconnect()
      observer = null
    }
    if (chartInstance.value) {
      chartInstance.value.dispose()
      chartInstance.value = null
    }
  })

  return { chartRef, render, resize, chartInstance }
}

export { echarts }
export default useChart
