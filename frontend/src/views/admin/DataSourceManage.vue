<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">
        数据源管理
        <button class="moa-btn ghost" @click="loadList()">刷新</button>
      </h3>
      <div v-if="state.error" class="moa-error">{{ state.error }}</div>
      <div v-if="state.loading" class="moa-loading">加载中…</div>
      <table v-else class="moa-table">
        <thead>
          <tr><th>数据源</th><th>类型</th><th>源系统</th><th>目标 ODS 表</th><th>装载模式</th><th>文件可用</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in state.sources" :key="row.source_name">
            <td>{{ row.source_name }}</td>
            <td>{{ row.source_type }}</td>
            <td>{{ row.system_type }}</td>
            <td>{{ row.target_table }}</td>
            <td>{{ row.load_mode }}</td>
            <td>
              <span :class="['moa-tag', row.available ? 'ok' : 'danger']">
                {{ row.available ? '可用' : '缺失' }}
              </span>
            </td>
            <td>
              <button class="moa-btn ghost small" :disabled="state.testing === row.source_name" @click="submitForm(row)">
                测试连接
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="state.message" class="moa-tag ok">{{ state.message }}</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 数据源管理页（阶段五 · 步骤 3-4）
 * loadList()   加载数据源清单（来自 etl/config/sources.json）
 * submitForm() 数据源连通性测试提交（文件类校验表头，数据库类探测连接）
 */
import { onMounted, reactive } from 'vue'
import { systemApi } from '@/api/modules'

const state = reactive({ loading: false, testing: '', error: '', message: '', sources: [] })

async function loadList() {
  state.loading = true
  state.error = ''
  try {
    state.sources = await systemApi.dataSources()
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }
}

async function submitForm(row) {
  state.testing = row.source_name
  state.error = ''
  state.message = ''
  try {
    const result = await systemApi.testDataSource(row.source_name)
    state.message = `${row.source_name}：${result.message}`
  } catch (error) {
    state.error = `${row.source_name} 连接测试失败：${error.message}`
  } finally {
    state.testing = ''
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
