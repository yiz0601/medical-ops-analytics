/**
 * 接口封装（阶段五 · 步骤 1-1）
 * 按后端模块组织：认证 / 驾驶舱 / 五大主题 / 报表导出 / 任务质量 / 系统管理 / 智能分析
 */
import request from './request'

// ---------------------------------------------------------------- 认证
export const authApi = {
  login: (payload) => request.post('/auth/login', payload),
  profile: () => request.get('/auth/profile'),
  listUsers: () => request.get('/auth/users'),
  createUser: (payload) => request.post('/auth/users', payload),
  updateUser: (userId, payload) => request.put(`/system/users/${userId}`, payload)
}

// ---------------------------------------------------------------- 驾驶舱与主题
export const dashboardApi = {
  overview: (params) => request.get('/dashboard/overview', { params }),
  dept: (params) => request.get('/dashboard/dept', { params }),
  exportFile: (params) =>
    request.get('/dashboard/export', { params, responseType: 'blob' })
}

/** 主题指标查询（outpatient / inpatient / revenue / disease / resource） */
export function themeMetrics(theme, params) {
  return request.get(`/${theme}/metrics`, { params })
}

// ---------------------------------------------------------------- 任务与质量
export const taskApi = {
  status: () => request.get('/task/status'),
  trigger: (payload) => request.post('/task/trigger', payload),
  qualityReport: (params) => request.get('/quality/report', { params })
}

// ---------------------------------------------------------------- 系统管理
export const systemApi = {
  roles: () => request.get('/system/roles'),
  dataSources: () => request.get('/system/datasources'),
  testDataSource: (name) => request.post(`/system/datasources/${name}/test`),
  audits: (params) => request.get('/system/audits', { params }),
  alerts: (params) => request.get('/system/alerts', { params }),
  alertTimeliness: (params) => request.get('/system/alerts/timeliness', { params }),
  readAlert: (alertId) => request.post(`/system/alerts/${alertId}/read`),
  readAllAlerts: () => request.post('/system/alerts/read-all')
}

// ---------------------------------------------------------------- 智能分析
export const aiApi = {
  capabilities: () => request.get('/llm/capabilities'),
  query: (question) => request.post('/llm/query', { question }),
  report: (payload) => request.post('/llm/report', payload),
  kb: (question) => request.post('/llm/kb', { question }),
  anomaly: (payload) => request.post('/llm/anomaly', payload)
}

export default { authApi, dashboardApi, themeMetrics, taskApi, systemApi, aiApi }
