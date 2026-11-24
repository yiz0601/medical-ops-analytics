<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">
        角色与权限
        <button class="moa-btn ghost" @click="loadList()">刷新</button>
      </h3>
      <div v-if="state.error" class="moa-error">{{ state.error }}</div>
      <div v-if="state.loading" class="moa-loading">加载中…</div>
      <table v-else class="moa-table">
        <thead>
          <tr><th>角色编码</th><th>角色名称</th><th>说明</th><th>权限点</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="role in state.roles" :key="role.role_code">
            <td>{{ role.role_code }}</td>
            <td>{{ role.role_name }}</td>
            <td>{{ role.description }}</td>
            <td>
              <span v-for="perm in role.permissions" :key="perm" class="moa-tag">{{ perm }}</span>
            </td>
            <td><button class="moa-btn ghost small" @click="edit(role)">编辑权限</button></td>
          </tr>
        </tbody>
      </table>
      <p class="hint">
        说明：角色目录由后端预置（RBAC 三角色），本页权限矩阵调整仅在本浏览器生效——角色/权限持久化接口属阶段七扩展项。
      </p>
    </div>

    <div v-if="form.role_code" class="moa-card">
      <h3 class="moa-card-title">编辑权限：{{ form.role_name }}（{{ form.role_code }}）</h3>
      <div class="moa-form-row">
        <label v-for="perm in allPermissions" :key="perm" class="perm-check">
          <input v-model="form.permissions" type="checkbox" :value="perm" /> {{ perm }}
        </label>
      </div>
      <div class="moa-form-row">
        <button class="moa-btn" @click="submitForm()">提交</button>
        <button class="moa-btn ghost" @click="form.role_code = ''">取消</button>
      </div>
      <p v-if="state.message" class="moa-tag ok">{{ state.message }}</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 角色管理页（阶段五 · 步骤 3-3）
 * loadList()   加载角色目录
 * submitForm() 角色权限配置提交（浏览器本地保存，接口待阶段七扩展）
 */
import { onMounted, reactive } from 'vue'
import { systemApi } from '@/api/modules'

const STORAGE_KEY = 'moa_role_permissions'
const allPermissions = ['user:manage', 'system:manage', 'data:all', 'data:dept', 'task:trigger', 'export:all', 'quality:view', 'dashboard:view']

const state = reactive({ loading: false, error: '', message: '', roles: [] })
const form = reactive({ role_code: '', role_name: '', permissions: [] })

function localOverrides() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch (error) {
    return {}
  }
}

async function loadList() {
  state.loading = true
  state.error = ''
  try {
    const roles = await systemApi.roles()
    const overrides = localOverrides()
    state.roles = roles.map((role) => ({
      ...role,
      permissions: overrides[role.role_code] || role.permissions
    }))
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }
}

function edit(role) {
  form.role_code = role.role_code
  form.role_name = role.role_name
  form.permissions = [...role.permissions]
}

function submitForm() {
  const overrides = localOverrides()
  overrides[form.role_code] = [...form.permissions]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides))
  state.message = `${form.role_name} 权限已保存（本地演示）`
  loadList()
}

onMounted(() => loadList())
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: #98a2b3;
  margin: 10px 0 0;
}

.perm-check {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #3d4757;
}

.moa-btn.small {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
