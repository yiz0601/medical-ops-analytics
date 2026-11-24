/**
 * HTTP 请求封装与拦截器（阶段五 · 步骤 1-1）
 * - baseURL 读取 VITE_API_BASE（默认 /api），开发环境由 Vite 代理、生产由 Nginx 反代
 * - 请求拦截：自动注入 Authorization: Bearer <token>
 * - 响应拦截：解包统一外壳 {code,msg,data}；401 清除本地状态并跳转 /login（带 redirect）
 */
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

let onUnauthorized = null

/** 由 store 注册 401 回调，避免循环依赖 */
export function registerUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('moa_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

request.interceptors.response.use(
  (response) => {
    // 文件流（导出）直接返回原始响应
    if (response.config.responseType === 'blob') {
      return response
    }
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) {
        return body.data
      }
      return Promise.reject(new Error(body.msg || `业务错误 ${body.code}`))
    }
    return body
  },
  (error) => {
    const status = error?.response?.status
    const body = error?.response?.data
    const message = body?.msg || error.message || '请求失败'
    if (status === 401) {
      if (typeof onUnauthorized === 'function') {
        onUnauthorized()
      }
    }
    return Promise.reject(new Error(`${status ? `[${status}] ` : ''}${message}`))
  }
)

export default request
export { API_BASE }
