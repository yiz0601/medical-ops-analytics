import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useUserStore } from './store/user'
import { registerUnauthorizedHandler } from './api/request'
import theme from './styles/theme'
import './styles/global.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 全局错误兜底：避免未捕获异常导致白屏
app.config.errorHandler = (error, instance, info) => {
  // eslint-disable-next-line no-console
  console.error('[app error]', info, error)
}

// 401 统一处理：清空登录态并跳转登录页（携带 redirect）
registerUnauthorizedHandler(() => {
  const user = useUserStore(pinia)
  const redirect = encodeURIComponent(window.location.pathname + window.location.search)
  user.setToken('')
  user.setUser(null)
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = `/login?redirect=${redirect}`
  }
})

// 恢复本地登录态
useUserStore(pinia).restore()

// 主题变量注入（供全局样式使用）
document.documentElement.style.setProperty('--moa-primary', theme.primary)
document.documentElement.style.setProperty('--moa-bg', theme.bg)

app.mount('#app')
