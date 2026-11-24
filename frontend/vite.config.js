import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 医疗运营数据主题分析平台前端构建配置
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // 开发环境把 /api 代理到后端（生产由 Nginx 反代）
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // 按需分包：ECharts 与 Vue 生态独立，减小首屏体积
        manualChunks: {
          echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
          vue: ['vue', 'vue-router', 'pinia']
        }
      }
    }
  }
})
