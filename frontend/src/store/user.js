/**
 * 用户状态管理（阶段五 · 步骤 1-3）
 * - token 与用户信息持久化到 localStorage，初始化时自动恢复
 * - login / fetchProfile / logout（清空本地状态并跳转登录页）
 */
import { defineStore } from 'pinia'
import { authApi } from '@/api/modules'

const TOKEN_KEY = 'moa_token'
const USER_KEY = 'moa_user'

const ROLE_LABELS = {
  ADMIN: '管理员',
  ANALYST: '运营分析师',
  DEPT_USER: '科室用户'
}

function readUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (error) {
    return null
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: readUser(),
    loading: false
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    role: (state) => state.user?.role_code || '',
    roleLabel: (state) => ROLE_LABELS[state.user?.role_code] || '未登录',
    username: (state) => state.user?.username || '',
    realName: (state) => state.user?.real_name || state.user?.username || '',
    deptCode: (state) => state.user?.dept_code || '',
    isAdmin: (state) => state.user?.role_code === 'ADMIN',
    isDeptUser: (state) => state.user?.role_code === 'DEPT_USER'
  },
  actions: {
    /** 写入令牌并持久化 */
    setToken(token) {
      this.token = token || ''
      if (token) {
        localStorage.setItem(TOKEN_KEY, token)
      } else {
        localStorage.removeItem(TOKEN_KEY)
      }
    },
    /** 写入用户信息并持久化 */
    setUser(user) {
      this.user = user || null
      if (user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user))
      } else {
        localStorage.removeItem(USER_KEY)
      }
    },
    /** 登录：换取令牌并保存用户信息 */
    async login(payload) {
      this.loading = true
      try {
        const data = await authApi.login(payload)
        this.setToken(data.access_token)
        this.setUser(data.user)
        return data
      } finally {
        this.loading = false
      }
    },
    /** 拉取当前用户信息（刷新页面后校验令牌有效性） */
    async fetchProfile() {
      const profile = await authApi.profile()
      this.setUser(profile)
      return profile
    },
    /** 清空本地状态并跳转登录页 */
    logout(redirect = true) {
      this.setToken('')
      this.setUser(null)
      if (redirect) {
        window.location.href = '/login'
      }
    },
    /** 恢复本地状态（应用启动时调用） */
    restore() {
      this.token = localStorage.getItem(TOKEN_KEY) || ''
      this.user = readUser()
    }
  }
})

export { ROLE_LABELS }
export default useUserStore
