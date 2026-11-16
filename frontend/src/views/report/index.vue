<template>
  <section class="page" data-module="report">
    <header class="page-head">
      <div>
        <h2>经营分析报告管理</h2>
        <p class="page-desc">维护经营分析的模板选择、关键发现与分发管理，为经营分析报告提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记分析报告</button>
        <button class="btn" type="button" @click="exportRows">导出经营分析报告清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="viewSnapshots(row)">取数依据</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无经营分析报告数据，可先登记分析报告</td>
        </tr>
      </tbody>
    </table>

    <div v-if="snapshotPanel.report" class="snapshot-panel">
      <div class="snapshot-head">
        <strong>{{ snapshotPanel.report['报告编号'] }} 的取数依据（来自已发布经营明细数据集，不可变）</strong>
        <button class="btn ghost" type="button" @click="snapshotPanel.report = null">关闭</button>
      </div>
      <table v-if="snapshotPanel.items.length" class="data-table">
        <thead>
          <tr><th>快照</th><th>数据版本</th><th>明细数</th><th>币种合计</th><th>未计冲突组</th><th>来源范围</th><th>生成时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in snapshotPanel.items" :key="snapshot.snapshot_id">
            <td>{{ snapshot.snapshot_id }}</td>
            <td>{{ snapshot.dataset_version }}</td>
            <td>{{ snapshot.record_count }}</td>
            <td>
              <span v-for="total in snapshot.total_by_currency" :key="total.currency">
                {{ total.currency }} {{ total.amount }}；
              </span>
            </td>
            <td>{{ snapshot.excluded_conflict_count }}</td>
            <td>
              <span v-for="scope in snapshot.source_scope" :key="scope.file_id">
                {{ scope.source_name }}/{{ scope.filename }}；
              </span>
            </td>
            <td>{{ snapshot.created_at }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">该报告还没有取数快照，请先到「多源经营明细导入」发布数据集并生成快照</p>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条经营分析报告记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/report'
const columns = ["报告编号", "报告主题", "分析周期", "报告模板", "关键发现", "数据附件", "分发对象", "报告状态"]
const actions = ["生成报告", "分发报告", "归档报告"]
const statuses = ["草稿", "已生成", "已分发", "已归档"]
const stats = [{"label": "分析报告总数", "value": 0}, {"label": "已生成报告", "value": 0}, {"label": "已分发报告", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const snapshotPanel = reactive<{ report: Row | null; items: any[] }>({ report: null, items: [] })

async function viewSnapshots(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/snapshots`)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail ?? '取数依据读取失败')
    }
    const payload = await response.json()
    snapshotPanel.report = row
    snapshotPanel.items = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '取数依据读取失败'
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '分析报告登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('经营分析报告动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '经营分析报告操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('分析报告列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '经营分析报告列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.snapshot-panel {
  margin-top: 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.snapshot-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}
</style>
