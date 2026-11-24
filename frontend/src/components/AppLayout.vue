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
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { routes } from '@/router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

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
