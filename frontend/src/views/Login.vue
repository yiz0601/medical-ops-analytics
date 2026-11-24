<template>
  <div class="login-page">
    <div class="login-card">
      <h2>医疗运营数据主题分析平台</h2>
      <p class="subtitle">面向医院运营管理部门的一站式数据分析平台</p>

      <form @submit.prevent="handleSubmit">
        <label class="field">
          <span>账号</span>
          <input v-model="form.username" class="moa-input" autocomplete="username" placeholder="请输入账号" />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="form.password" type="password" class="moa-input" autocomplete="current-password" placeholder="请输入密码" />
        </label>

        <button class="moa-btn submit" :disabled="user.loading" type="submit">
          {{ user.loading ? '登录中…' : '登 录' }}
        </button>
      </form>

      <p v-if="error" class="moa-error">{{ error }}</p>

      <div class="demo-hint">
        <strong>演示账号</strong>
        <ul>
          <li>管理员：<code>admin / Admin@123</code>（全院 + 系统管理）</li>
          <li>运营分析师：<code>analyst01 / Analyst@123</code>（全院分析 + 报表）</li>
          <li>科室用户：<code>dept_hn / Dept@123</code>（仅呼吸内科数据）</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 登录页（阶段五 · 步骤 1-2 配套）
 * 登录成功后跳转 redirect 参数指定页面，默认进入管理驾驶舱。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const user = useUserStore()

const form = reactive({ username: 'admin', password: 'Admin@123' })
const error = ref('')

async function handleSubmit() {
  error.value = ''
  if (!form.username || !form.password) {
    error.value = '请输入账号与密码'
    return
  }
  try {
    await user.login({ username: form.username, password: form.password })
    const redirect = route.query.redirect ? decodeURIComponent(String(route.query.redirect)) : '/dashboard'
    router.push(redirect)
  } catch (err) {
    error.value = err.message || '登录失败，请检查账号密码'
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2937 0%, #2f6fd0 100%);
}

.login-card {
  width: 380px;
  background: #ffffff;
  border-radius: 10px;
  padding: 28px 30px 22px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.24);
}

h2 {
  margin: 0 0 6px;
  font-size: 18px;
}

.subtitle {
  margin: 0 0 18px;
  font-size: 12px;
  color: #6b7785;
}

.field {
  display: block;
  margin-bottom: 12px;
}

.field span {
  display: block;
  font-size: 12px;
  color: #6b7785;
  margin-bottom: 4px;
}

.field .moa-input {
  width: 100%;
  height: 36px;
}

.submit {
  width: 100%;
  height: 38px;
  margin-top: 6px;
}

.demo-hint {
  margin-top: 16px;
  font-size: 12px;
  color: #6b7785;
  border-top: 1px dashed #e5e8ef;
  padding-top: 12px;
}

.demo-hint ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.demo-hint code {
  color: #2f6fd0;
}
</style>
