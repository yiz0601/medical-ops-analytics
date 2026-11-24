<template>
  <div class="moa-layout">
    <aside class="moa-sidebar">
      <div class="moa-logo">医疗运营数据<br />主题分析平台</div>

      <template v-for="group in menuGroups" :key="group.name">
        <div v-if="group.name" class="moa-menu-group">{{ group.name }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="moa-menu-item"
          :class="{ active: route.path === item.path }"
        >
          <span>{{ item.icon }}</span>
          <span>{{ item.title }}</span>
        </router-link>
      </template>
    </aside>

    <div class="moa-main">
      <header class="moa-header">
        <h1>{{ route.meta?.title || '医疗运营数据主题分析平台' }}</h1>
        <div class="moa-header-right">
          <!-- 质量告警站内信（含未读数与及时率） -->
          <div class="alert-bell">
            <button class="moa-btn ghost" :title="`质量告警站内信（未读 ${alertState.unread}）`" @click="toggleAlerts()">
              🔔<span v-if="alertState.unread" class="alert-badge">{{ alertState.unread }}</span>
            </button>
            <div v-if="alertState.open" class="alert-panel">
              <div class="alert-head">
                <strong>质量告警</strong>
                <span class="alert-rate">
                  通知及时率 {{ alertState.timeliness?.timeliness_rate ?? 100 }}%
                  （{{ alertState.timeliness?.timely ?? 0 }}/{{ alertState.timeliness?.total ?? 0 }}）
                </span>
                <button class="moa-btn ghost small" @click="readAll()">全部已读</button>
              </div>
              <div v-if="!alertState.items.length" class="alert-empty">暂无告警</div>
              <ul v-else class="alert-list">
                <li v-for="item in alertState.items" :key="item.id" :class="['alert-item', { unread: !item.is_read }]">
                  <div class="alert-line">
                    <span :class="['moa-tag', item.level === 'BLOCK' ? 'danger' : 'warn']">{{ item.level }}</span>
                    <span class="alert-code">{{ item.rule_code }} · {{ item.rule_name }}</span>
                    <span class="alert-time">{{ item.notified_at || item.created_at }}</span>
                  </div>
                  <p class="alert-detail">{{ item.table_name }}：{{ item.detail }}</p>
                  <button v-if="!item.is_read" class="moa-btn ghost small" @click="readOne(item)">标记已读</button>
                </li>
              </ul>
            </div>
          </div>
          <span v-if="user.deptCode" class="moa-tag">数据范围：{{ user.deptCode }}</span>
          <span class="moa-role-tag">{{ user.roleLabel }}</span>
          <span>{{ user.realName }}</span>
          <button class="moa-btn ghost" @click="handleLogout">退出</button>
        </div>
      </header>
      <main class="moa-content">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup>
/**
 * 应用布局（阶段五 · 步骤 1-2 配套）
 * 侧边菜单根据路由 meta 与当前角色动态生成：科室用户看不到管理页。
 * 页头右侧为质量告警站内信：展示未读数、告警清单与通知及时率（GET /api/system/alerts）。
 */
import { computed, onBeforeUnmount, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { routes } from '@/router'
import { systemApi } from '@/api/modules'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

const alertState = reactive({ open: false, unread: 0, items: [], timeliness: null, error: '' })
let alertTimer = null

/** 拉取告警（未读数 + 最近 5 条 + 及时率） */
async function loadAlerts() {
  if (!user.isLoggedIn) return
  try {
    const data = await systemApi.alerts({ limit: 5 })
    alertState.items = data.items || []
    alertState.unread = data.unread ?? 0
    alertState.timeliness = data.timeliness || null
    alertState.error = ''
  } catch (error) {
    alertState.error = error.message || '告警加载失败'
  }
}

function toggleAlerts() {
  alertState.open = !alertState.open
  if (alertState.open) loadAlerts()
}

async function readOne(item) {
  await systemApi.readAlert(item.id)
  await loadAlerts()
}

async function readAll() {
  await systemApi.readAllAlerts()
  await loadAlerts()
}

onMounted(() => {
  loadAlerts()
  alertTimer = window.setInterval(loadAlerts, 60000)
})

onBeforeUnmount(() => {
  if (alertTimer) window.clearInterval(alertTimer)
})

const menuGroups = computed(() => {
  const visible = routes.filter((item) => {
    if (item.meta?.public || !item.meta?.title) return false
    const roles = item.meta?.roles
    return !Array.isArray(roles) || roles.includes(user.role)
  })
  const business = visible.filter((item) => !item.meta?.group)
  const admin = visible.filter((item) => item.meta?.group === '管理')
  const groups = [{ name: '', items: business }]
  if (admin.length) {
    groups.push({ name: '系统管理', items: admin })
  }
  return groups
})

function handleLogout() {
  user.logout(false)
  router.push('/login')
}
</script>

<style scoped>
.alert-bell {
  position: relative;
  margin-right: 8px;
}

.alert-badge {
  display: inline-block;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 8px;
  background: #d9534f;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}

.alert-panel {
  position: absolute;
  top: 34px;
  right: 0;
  z-index: 30;
  width: 420px;
  max-height: 420px;
  overflow-y: auto;
  padding: 12px;
  background: #fff;
  border: 1px solid #e5e8ef;
  border-radius: 10px;
  box-shadow: 0 12px 30px rgba(31, 39, 51, 0.14);
}

.alert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eef1f6;
  font-size: 12px;
  color: #6b7785;
}

.alert-rate {
  color: #2fa36b;
}

.alert-empty {
  padding: 16px 0;
  text-align: center;
  color: #98a2b3;
  font-size: 12px;
}

.alert-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.alert-item {
  padding: 10px 0;
  border-bottom: 1px dashed #eef1f6;
}

.alert-item.unread {
  background: #f7fafd;
}

.alert-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.alert-code {
  flex: 1;
  color: #1f2733;
}

.alert-time {
  color: #98a2b3;
}

.alert-detail {
  margin: 6px 0;
  font-size: 12px;
  color: #6b7785;
  line-height: 1.5;
  word-break: break-all;
}
</style>
