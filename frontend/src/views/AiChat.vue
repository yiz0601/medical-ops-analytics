<template>
  <div>
    <div class="moa-card">
      <h3 class="moa-card-title">
        智能问数（NL2SQL）
        <span class="moa-tag" :class="state.llmAvailable ? 'ok' : 'warn'">
          {{ state.llmAvailable ? '已接入大模型' : '离线规则引擎' }}
        </span>
      </h3>
      <div class="moa-form-row">
        <input
          v-model="question"
          class="moa-input question-input"
          placeholder="例如：上月呼吸科床位使用率趋势如何"
          @keyup.enter="ask()"
        />
        <button class="moa-btn" :disabled="state.loading" @click="ask()">提问</button>
        <button class="moa-btn ghost" @click="mode = mode === 'query' ? 'kb' : 'query'">
          切换到{{ mode === 'query' ? '口径问答' : '智能问数' }}
        </button>
      </div>
      <div class="moa-form-row">
        <span class="example-label">示例：</span>
        <button v-for="item in state.examples" :key="item" class="moa-btn ghost small" @click="useExample(item)">
          {{ item }}
        </button>
      </div>
    </div>

    <div v-if="state.error" class="moa-error">{{ state.error }}</div>

    <!-- 问数结果 -->
    <template v-if="mode === 'query' && state.result">
      <div class="moa-card">
        <h3 class="moa-card-title">解读</h3>
        <p class="insight">{{ state.result.insight }}</p>
        <div class="meta-row">
          <span class="moa-tag">{{ state.result.intent.metric_code }} {{ state.result.intent.metric_name }}</span>
          <span class="moa-tag">维度 {{ state.result.intent.dim_name }}</span>
          <span class="moa-tag">粒度 {{ state.result.intent.granularity }}</span>
          <span class="moa-tag">置信度 {{ (state.result.intent.confidence * 100).toFixed(0) }}%</span>
          <span class="moa-tag">{{ state.result.row_count }} 行</span>
        </div>
        <details class="sql-box">
          <summary>查看生成的 SQL（只读，已通过白名单校验）</summary>
          <pre>{{ state.result.sql }}</pre>
        </details>
      </div>

      <div class="moa-grid cols-2">
        <div class="moa-card">
          <h3 class="moa-card-title">图表</h3>
          <TrendChart
            v-if="state.result.chart.type === 'trend_line'"
            :data="trendPayload"
            :unit="unitOf"
            :series-name="state.result.intent.metric_name"
          />
          <RankBar v-else-if="state.result.chart.type === 'rank_bar'" :data="rankPayload" :unit="unitOf" />
          <KpiCard v-else :data="kpiPayload" />
        </div>
        <div class="moa-card">
          <h3 class="moa-card-title">明细</h3>
          <table class="moa-table">
            <thead>
              <tr><th>科室</th><th>统计日期</th><th class="num">数值</th><th>单位</th><th>状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in state.result.data" :key="index">
                <td>{{ row.dept_name }}</td>
                <td>{{ row.stat_date }}</td>
                <td class="num">{{ row.metric_value === null ? '—' : row.metric_value }}</td>
                <td>{{ row.unit }}</td>
                <td>
                  <span :class="['moa-tag', row.data_status === 'PENDING' ? 'warn' : 'ok']">
                    {{ row.data_status === 'PENDING' ? '待补充' : '正常' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 口径问答结果 -->
    <template v-if="mode === 'kb' && state.kb">
      <div class="moa-card">
        <h3 class="moa-card-title">口径解答</h3>
        <p class="insight">{{ state.kb.answer }}</p>
        <div v-if="state.kb.refs?.length" class="meta-row">
          <span class="example-label">引用：</span>
          <span v-for="ref in state.kb.refs" :key="ref.title" class="moa-tag">{{ ref.title }}</span>
        </div>
        <p v-if="!state.kb.matched" class="moa-tag warn">手册未收录该口径，未做猜测</p>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * 智能问数页（阶段六配套前端）
 * 支持自然语言问数（返回数值 + 图表 + 解读）与指标口径问答两种模式。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import KpiCard from '@/components/charts/KpiCard.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import RankBar from '@/components/charts/RankBar.vue'
import { aiApi } from '@/api/modules'

const question = ref('上月呼吸科床位使用率趋势如何')
const mode = ref('query')
const state = reactive({
  loading: false,
  error: '',
  result: null,
  kb: null,
  examples: [],
  llmAvailable: false
})

const unitOf = computed(() => state.result?.data?.[0]?.unit || '')
const trendPayload = computed(() =>
  (state.result?.data || []).map((row) => ({ stat_date: row.stat_date, metric_value: row.metric_value }))
)
const rankPayload = computed(() =>
  (state.result?.data || []).map((row) => ({ name: row.dept_name, dept_code: row.dim_value, value: row.metric_value }))
)
const kpiPayload = computed(() => {
  const row = state.result?.data?.[0] || {}
  return {
    code: state.result?.intent?.metric_code,
    title: state.result?.intent?.metric_name,
    metric_value: row.metric_value,
    unit: row.unit,
    data_status: row.data_status
  }
})

function useExample(text) {
  question.value = text
  ask()
}

async function ask() {
  if (!question.value || state.loading) return
  state.loading = true
  state.error = ''
  try {
    if (mode.value === 'query') {
      state.result = await aiApi.query(question.value)
      state.kb = null
    } else {
      state.kb = await aiApi.kb(question.value)
      state.result = null
    }
  } catch (error) {
    state.error = error.message || '请求失败'
  } finally {
    state.loading = false
  }
}

onMounted(async () => {
  try {
    const caps = await aiApi.capabilities()
    state.examples = (caps.examples || []).slice(0, 4)
    state.llmAvailable = Boolean(caps.llm_available)
  } catch (error) {
    state.examples = []
  }
})
</script>

<style scoped>
.question-input {
  flex: 1;
  min-width: 280px;
}

.example-label {
  font-size: 12px;
  color: #98a2b3;
}

.moa-btn.small {
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
}

.insight {
  font-size: 13px;
  line-height: 1.7;
  color: #1f2733;
  margin: 0 0 8px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.sql-box {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7785;
}

.sql-box pre {
  background: #f7f9fc;
  border: 1px solid #eef1f6;
  border-radius: 6px;
  padding: 10px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
