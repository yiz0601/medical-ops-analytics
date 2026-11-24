/**
 * 路由与全局守卫（阶段五 · 步骤 1-2）
 * - routes 常量数组：按业务域组织页面路径，meta 携带标题、图标与所需角色
 * - router.beforeEach：未登录访问受保护页面重定向到 /login 并携带 redirect 参数；
 *   角色不足（如科室用户访问管理页）重定向到驾驶舱
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '管理驾驶舱', icon: '📊', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/dept-board',
    name: 'dept-board',
    component: () => import('@/views/DeptBoard.vue'),
    meta: { title: '科室运营看板', icon: '🏨', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/outpatient',
    name: 'outpatient',
    component: () => import('@/views/Outpatient.vue'),
    meta: { title: '门诊分析', icon: '🏥', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/inpatient',
    name: 'inpatient',
    component: () => import('@/views/Inpatient.vue'),
    meta: { title: '住院分析', icon: '🛏️', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/revenue',
    name: 'revenue',
    component: () => import('@/views/Revenue.vue'),
    meta: { title: '收入分析', icon: '💰', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/disease',
    name: 'disease',
    component: () => import('@/views/Disease.vue'),
    meta: { title: '病种分析', icon: '🧬', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/resource',
    name: 'resource',
    component: () => import('@/views/Resource.vue'),
    meta: { title: '资源效率', icon: '⚙️', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/report',
    name: 'report',
    component: () => import('@/views/ReportCenter.vue'),
    meta: { title: '报表中心', icon: '🧾', roles: ['ADMIN', 'ANALYST'] }
  },
  {
    path: '/ai',
    name: 'ai',
    component: () => import('@/views/AiChat.vue'),
    meta: { title: '智能问数', icon: '🤖', roles: ['ADMIN', 'ANALYST', 'DEPT_USER'] }
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/admin/UserManage.vue'),
    meta: { title: '用户管理', icon: '👤', roles: ['ADMIN'], group: '管理' }
  },
  {
    path: '/admin/roles',
    name: 'admin-roles',
    component: () => import('@/views/admin/RoleManage.vue'),
    meta: { title: '角色管理', icon: '🛡️', roles: ['ADMIN'], group: '管理' }
  },
  {
    path: '/admin/datasources',
    name: 'admin-datasources',
    component: () => import('@/views/admin/DataSourceManage.vue'),
    meta: { title: '数据源管理', icon: '🗄️', roles: ['ADMIN'], group: '管理' }
  },
  {
    path: '/admin/tasks',
    name: 'admin-tasks',
    component: () => import('@/views/admin/TaskManage.vue'),
    meta: { title: '任务管理', icon: '⏱️', roles: ['ADMIN'], group: '管理' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面不存在', public: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach((to) => {
  const user = useUserStore()
  document.title = to.meta?.title ? `${to.meta.title} · 医疗运营分析平台` : '医疗运营数据主题分析平台'

  // 已登录用户访问登录页 → 直接进驾驶舱
  if (to.meta?.public && to.name === 'login' && user.isLoggedIn) {
    return { path: '/dashboard' }
  }
  if (to.meta?.public) {
    return true
  }
  if (!user.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  const roles = to.meta?.roles
  if (Array.isArray(roles) && roles.length && !roles.includes(user.role)) {
    return { path: '/dashboard' }
  }
  return true
})

export default router
