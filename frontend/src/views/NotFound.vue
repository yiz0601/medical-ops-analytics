<template>
  <div class="not-found">
    <h2>404</h2>
    <p>页面不存在或已被移动</p>
    <router-link class="moa-btn" to="/dashboard">返回管理驾驶舱</router-link>
  </div>
</template>

<script setup>
/** 404 页面 */
</script>

<style scoped>
.not-found {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #6b7785;
}

.not-found h2 {
  font-size: 42px;
  margin: 0;
  color: #2f6fd0;
}
</style>
