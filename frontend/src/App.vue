<template>
  <AppLayout v-if="!isPublic"><router-view /></AppLayout>
  <router-view v-else />
</template>

<script setup>
/**
 * 根组件：登录页等公开页面直接渲染，其余页面套用统一布局（侧边导航 + 顶栏）。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'

const route = useRoute()
const isPublic = computed(() => Boolean(route.meta?.public))
</script>
