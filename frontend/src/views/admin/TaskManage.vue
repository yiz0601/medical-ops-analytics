<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">
        采集 / 计算任务
        <button class="moa-btn ghost" @click="loadList()">刷新</button>
      </h3>
      <div v-if="state.error" class="moa-error">{{ state.error }}</div>
      <div v-if="state.loading" class="moa-loading">加载中…</div>
      <table v-else class="moa-table">
        <thead>
          <tr><th>任务</th><th>状态</th><th class="num">行数</th><th class="num">耗时(ms)</th><th>日志时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in state.tasks" :key="row.task_name">
            <td>{{ row.task_name }}</td>
            <td>
              <span :class="['moa-tag', row.status === 'SUCCESS' ? 'ok' : row.status === 'FAILED' ? 'danger' : 'warn']">
                {{ row.status }}
              </span>
            </td>
            <td class="num">{{ row.rows }}</td>
            <td class="num">{{ row.cost_ms.toFixed(0) }}</td>
            <td>{{ row.log_time || '—' }}</td>
            <td>
              <button
                v-if="triggerable.includes(row.task_name)"
                class="moa-btn ghost small"
                :disabled="state.triggering === row.task_name"
                @click="triggerTask(row)"
              >
                手动触发
              </button>
              <span v-else class="moa-tag">只读校验</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="state.message" class="moa-tag ok">{{ state.message }}</p>
    </div>

    <div class="moa-card">
      <h3 class="moa-card-title">数据质量报告</h3>
      <div v-if="state.qualityError" class="moa-error">{{ state.qualityError }}</div>
      <div v-else-if="state.quality" class="quality-grid">
        <div><span class="label">批次</span><strong>{{ state.quality.batch_date || '—' }}</strong></div>
        <div><span class="label">评分</span><strong>{{ state.quality.score }}</strong></div>
        <div><span class="label">字段覆盖率</span><strong>{{ state.quality.coverage_rate }}%</strong></div>
        <div><span class="label">规则数</span><strong>{{ state.quality.total_rules }}</strong></div>
        <div><span class="label">通过 / 告警 / 失败</span><strong>{{ state.quality.passed }} / {{ state.quality.warn }} / {{ state.quality.failed }}</strong></div>
      </div>
      <table v-if="state.quality?.alerts?.length" class="moa-table">
        <thead>
          <tr><th>规则</th><th>对象</th><th>级别</th><th>明细</th></tr>
        </thead>
        <tbody>
          <tr v-for="alert in state.quality.alerts" :key="alert.rule_code">
            <td>{{ alert.rule_code }} {{ alert.rule_name }}</td>
            <td>{{ alert.table }}</td>
            <td><span class="moa-tag warn">{{ alert.level }}</span></td>
            <td>{{ alert.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
/**
 * 任务管理页（阶段五 · 步骤 3-5）
 * loadList()    加载采集/计算任务列表与状态（并读取最新质量报告）
 * triggerTask() 手动触发指定任务执行（管理员）
 */
import { onMounted, reactive } from 'vue'
import { taskApi } from '@/api/modules'

const triggerable = ['extract_ods', 'clean_dwd', 'dwd_wide', 'aggregate_dws', 'ads_indicators']

const state = reactive({
  loading: false,
  triggering: '',
  error: '',
  message: '',
  tasks: [],
  quality: null,
  qualityError: ''
})

async function loadList() {
  state.loading = true
  state.error = ''
  try {
    const data = await taskApi.status()
    state.tasks = data.tasks || []
  } catch (error) {
    state.error = error.message || '加载失败'
  } finally {
    state.loading = false
  }

  state.qualityError = ''
  try {
    state.quality = await taskApi.qualityReport({})
  } catch (error) {
    state.quality = null
    state.qualityError = `质量报告不可用：${error.message}（请先执行采集与质检任务）`
  }
}

async function triggerTask(row) {
  state.triggering = row.task_name
  state.error = ''
  state.message = ''
  try {
    const result = await taskApi.trigger({ task_name: row.task_name })
    state.message = `${result.task_name} 触发完成，处理 ${result.rows} 行`
    await loadList()
  } catch (error) {
    state.error = `触发失败：${error.message}`
  } finally {
    state.triggering = ''
  }
}

onMounted(() => loadList())
</script>

<style scoped>
.quality-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.quality-grid .label {
  display: block;
  font-size: 12px;
  color: #98a2b3;
}

@media (max-width: 900px) {
  .quality-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.moa-btn.small {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
</style>
