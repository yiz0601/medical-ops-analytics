<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">
        用户管理
        <button class="moa-btn ghost" @click="loadList()">刷新</button>
      </h3>
      <div v-if="state.error" class="moa-error">{{ state.error }}</div>
      <div v-if="state.loading" class="moa-loading">加载中…</div>
      <table v-else class="moa-table">
        <thead>
          <tr><th>账号</th><th>姓名</th><th>角色</th><th>科室</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in state.users" :key="row.id">
            <td>{{ row.username }}</td>
            <td>{{ row.real_name }}</td>
            <td>{{ row.role_code }}</td>
            <td>{{ row.dept_code || '—' }}</td>
            <td>{{ row.is_active === false ? '停用' : '启用' }}</td>
            <td><button class="moa-btn ghost small" @click="edit(row)">编辑</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="moa-card">
      <h3 class="moa-card-title">{{ form.id ? '编辑用户' : '新建用户' }}</h3>
      <div class="moa-form-row">
        <label>账号 <input v-model="form.username" class="moa-input" :disabled="Boolean(form.id)" /></label>
        <label>姓名 <input v-model="form.real_name" class="moa-input" /></label>
        <label>角色
          <select v-model="form.role_code" class="moa-select">
            <option value="ADMIN">管理员</option>
            <option value="ANALYST">运营分析师</option>
            <option value="DEPT_USER">科室用户</option>
          </select>
        </label>
        <label>科室
          <select v-model="form.dept_code" class="moa-select">
            <option value="">（全院，不填）</option>
            <option v-for="item in deptOptions" :key="item.code" :value="item.code">{{ item.name }}</option>
          </select>
        </label>
        <label v-if="!form.id">密码 <input v-model="form.password" type="password" class="moa-input" /></label>
        <label v-if="form.id">启用 <input v-model="form.is_active" type="checkbox" /></label>
        <button class="moa-btn" :disabled="state.saving" @click="submitForm()">提交</button>
        <button class="moa-btn ghost" @click="resetForm()">重置</button>
      </div>
      <p v-if="state.message" class="moa-tag ok">{{ state.message }}</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 用户管理页（阶段五 · 步骤 3-2）
 * loadList()   加载用户列表
 * submitForm() 用户新增/编辑提交并分配角色
 */
import { onMounted, reactive } from 'vue'
import { authApi } from '@/api/modules'
import { DEPT_OPTIONS } from '@/views/useThemeView'

const deptOptions = DEPT_OPTIONS.filter((item) => item.code !== 'ALL')

const state = reactive({ loading: false, saving: false, error: '', message: '', users: [] })
const form = reactive({ id: null, username: '', real_name: '', role_code: 'ANALYST', dept_code: '', password: '', is_active: true })

function resetForm() {
  Object.assign(form, { id: null, username: '', real_name: '', role_code: 'ANALYST', dept_code: '', password: '', is_active: true })
}

async function loadList() {
  state.loading = true
  state.error = ''
  try {
    state.users = await authApi.listUsers()
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }
}

function edit(row) {
  Object.assign(form, {
    id: row.id,
    username: row.username,
    real_name: row.real_name,
    role_code: row.role_code,
    dept_code: row.dept_code || '',
    is_active: row.is_active !== false
  })
}

async function submitForm() {
  state.error = ''
  state.message = ''
  state.saving = true
  try {
    if (form.id) {
      await authApi.updateUser(form.id, {
        role_code: form.role_code,
        dept_code: form.dept_code || null,
        real_name: form.real_name,
        is_active: form.is_active
      })
      state.message = '用户已更新'
    } else {
      if (!form.username || !form.password) throw new Error('账号与密码必填')
      if (form.role_code === 'DEPT_USER' && !form.dept_code) throw new Error('科室用户必须选择科室')
      await authApi.createUser({
        username: form.username,
        password: form.password,
        real_name: form.real_name,
        role_code: form.role_code,
        dept_code: form.dept_code || null
      })
      state.message = '用户已创建'
    }
    resetForm()
    await loadList()
  } catch (error) {
    state.error = error.message || '提交失败'
  } finally {
    state.saving = false
  }
}

onMounted(() => loadList())
</script>

<style scoped>
.moa-btn.small {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
