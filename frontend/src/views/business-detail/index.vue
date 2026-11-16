<template>
  <section class="page" data-module="business-detail">
    <header class="page-head">
      <div>
        <h2>多源经营明细导入</h2>
        <p class="page-desc">
          为接入配置导入本地经营明细（业务编号、所属周期、金额、币种），完成校验、去重与归并，
          发布成经营明细数据集，供经营分析报告按周期与币种取数并生成金额汇总附件。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="reloadAll">刷新数据</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <p v-if="message" class="notice" :class="{ 'notice-error': isError }">{{ message }}</p>

    <!-- 1. 文件导入 -->
    <div v-show="activeTab === 'import'" class="panel">
      <form class="import-form" @submit.prevent="submitImport">
        <label class="filter-item">
          <span>数据源名称（归属来源）</span>
          <input v-model="importForm.sourceName" placeholder="如：华东门店ERP" required />
        </label>
        <label class="filter-item">
          <span>关联接入配置 id（可选）</span>
          <input v-model.number="importForm.datasourceId" type="number" min="1" placeholder="如：1" />
        </label>
        <label class="filter-item file-pick">
          <span>本地明细文件（CSV，表头含 业务编号/所属周期/金额/币种）</span>
          <input type="file" accept=".csv,text/csv,text/plain" @change="pickFile" />
        </label>
        <button class="btn primary" type="submit" :disabled="!importForm.file || uploading">
          {{ uploading ? '导入中…' : '导入明细文件' }}
        </button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>批次</th><th>数据源</th><th>文件</th><th>导入时间</th>
            <th>有效行</th><th>无效行</th><th>状态</th><th>原始内容</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="batch in batches" :key="batch.id">
            <td>#{{ batch.id }}</td>
            <td>{{ batch.source_name }}</td>
            <td>{{ batch.filename }}</td>
            <td>{{ batch.imported_at }}</td>
            <td>{{ batch.valid_count }}</td>
            <td :class="{ 'cell-warn': batch.invalid_count > 0 }">{{ batch.invalid_count }}</td>
            <td>{{ batch.status }}</td>
            <td><button class="link" type="button" @click="viewBatch(batch.id)">查看原始文件</button></td>
          </tr>
          <tr v-if="!batches.length">
            <td colspan="8" class="empty-state">暂无导入批次，请先选择本地明细文件</td>
          </tr>
        </tbody>
      </table>

      <pre v-if="rawPreview" class="raw-preview">{{ rawPreview }}</pre>
    </div>

    <!-- 2. 无效行台账 -->
    <div v-show="activeTab === 'invalid'" class="panel">
      <p class="page-desc">无效金额、缺少业务编号或周期的行进此台账，可定位到原始文件与行号，绝不按零值参与汇总。</p>
      <table class="data-table">
        <thead>
          <tr><th>数据源</th><th>文件</th><th>原始行号</th><th>原始行内容</th><th>问题原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in invalidRows" :key="`${row.file_id}-${row.line_no}-${idx}`">
            <td>{{ row.source_name }}</td>
            <td>{{ row.filename }}</td>
            <td>第 {{ row.line_no }} 行</td>
            <td><code>{{ row.original_line }}</code></td>
            <td class="cell-warn">{{ row.reasons.join('；') }}</td>
          </tr>
          <tr v-if="!invalidRows.length">
            <td colspan="5" class="empty-state">没有无效行，导入数据全部通过校验</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 3. 归并与冲突裁决 -->
    <div v-show="activeTab === 'groups'" class="panel">
      <div class="filter-bar">
        <label class="filter-item">
          <span>归并状态</span>
          <select v-model="groupFilter" @change="loadGroups">
            <option value="">全部</option>
            <option value="一致">一致</option>
            <option value="冲突">冲突</option>
            <option value="已裁决">已裁决</option>
          </select>
        </label>
      </div>
      <p class="page-desc">
        同一业务编号跨来源归并为一组；口径一致只去重不累计，金额/周期/币种有分歧则标记冲突，
        未裁决前整组不参与汇总。源文件行序与导入先后不代表可信度。
      </p>
      <div v-for="group in groups" :key="group.id" class="group-card" :class="`status-${group.status}`">
        <div class="group-head">
          <strong>{{ group.biz_no }}</strong>
          <span class="tag">{{ group.status }}</span>
          <span class="tag" :class="group.included_in_summary ? 'tag-ok' : 'tag-off'">
            {{ group.included_in_summary ? '参与汇总' : '不参与汇总' }}
          </span>
          <span class="basis">依据：{{ group.basis }}</span>
        </div>
        <table class="data-table inner-table">
          <thead>
            <tr><th>候选</th><th>周期</th><th>币种</th><th>金额</th><th>来源/文件:行</th><th>角色</th><th>原始行</th></tr>
          </thead>
          <tbody>
            <tr v-for="candidate in group.candidates" :key="candidate.candidate_id">
              <td>#{{ candidate.candidate_id }}</td>
              <td>{{ candidate.period }}</td>
              <td>{{ candidate.currency }}</td>
              <td>{{ candidate.amount }}</td>
              <td>{{ candidate.source_name }} / {{ candidate.filename }}:{{ candidate.line_no }}</td>
              <td>{{ candidate.role }}</td>
              <td><code>{{ candidate.original_line }}</code></td>
            </tr>
          </tbody>
        </table>
        <form v-if="group.status === '冲突'" class="resolve-form" @submit.prevent="resolve(group)">
          <label class="filter-item">
            <span>入选候选</span>
            <select v-model="resolutionForms[group.id].candidateId" required>
              <option v-for="candidate in group.conflict_candidates" :key="candidate.candidate_id" :value="candidate.candidate_id">
                #{{ candidate.candidate_id }}（{{ candidate.source_name }}，{{ candidate.currency }} {{ candidate.amount }}）
              </option>
            </select>
          </label>
          <label class="filter-item grow">
            <span>裁决依据（必填，不允许无理由覆盖分歧数据）</span>
            <input v-model="resolutionForms[group.id].reason" placeholder="如：对账后以开票系统金额为准" required />
          </label>
          <label class="filter-item">
            <span>裁决人</span>
            <input v-model="resolutionForms[group.id].operator" placeholder="分析员" />
          </label>
          <button class="btn primary" type="submit">提交裁决</button>
        </form>
      </div>
      <p v-if="!groups.length" class="empty-state">暂无归并分组</p>
    </div>

    <!-- 4. 数据集发布 -->
    <div v-show="activeTab === 'datasets'" class="panel">
      <form class="filter-bar" @submit.prevent="publishCurrent">
        <label class="filter-item grow">
          <span>发布备注（可选）</span>
          <input v-model="publishRemark" placeholder="固化当前归并结果为不可变数据集版本" />
        </label>
        <button class="btn primary" type="button" @click="publishCurrent">发布新数据集版本</button>
      </form>
      <div v-for="dataset in datasets" :key="dataset.version" class="dataset-card">
        <div class="group-head">
          <strong>{{ dataset.version }}</strong>
          <span class="tag tag-ok">{{ dataset.status }}</span>
          <span>发布于 {{ dataset.published_at }}</span>
          <span>明细 {{ dataset.record_count }} 条 · 未计入冲突组 {{ dataset.conflict_group_count }} 个</span>
          <button class="link" type="button" @click="toggleDataset(dataset.version)">
            {{ expandedDatasets[dataset.version] ? '收起详情' : '查看详情与来源范围' }}
          </button>
        </div>
        <div v-if="expandedDatasets[dataset.version]" class="dataset-detail">
          <h4>按周期/币种金额汇总（币种不一致不混加）</h4>
          <table class="data-table inner-table">
            <thead><tr><th>所属周期</th><th>币种</th><th>汇总金额</th><th>明细条数</th></tr></thead>
            <tbody>
              <tr v-for="item in dataset.summaries" :key="`${item.period}-${item.currency}`">
                <td>{{ item.period }}</td><td>{{ item.currency }}</td><td>{{ item.amount }}</td><td>{{ item.record_count }}</td>
              </tr>
            </tbody>
          </table>
          <h4>来源范围（{{ dataset.source_scope.length }} 个来源文件）</h4>
          <ul class="scope-list">
            <li v-for="scope in dataset.source_scope" :key="scope.file_id">
              {{ scope.source_name }} / {{ scope.filename }}（指纹 {{ scope.fingerprint.slice(0, 12) }}…，{{ scope.uploaded_at }}）
            </li>
          </ul>
        </div>
      </div>
      <p v-if="!datasets.length" class="empty-state">尚未发布数据集，冲突处理完成后请发布新版本</p>
    </div>

    <!-- 5. 报告取数快照 -->
    <div v-show="activeTab === 'snapshots'" class="panel">
      <form class="filter-bar wrap" @submit.prevent="createSnapshot">
        <label class="filter-item">
          <span>经营分析报告 id</span>
          <input v-model.number="snapshotForm.reportId" type="number" min="1" required />
        </label>
        <label class="filter-item">
          <span>数据版本（留空取最新）</span>
          <input v-model="snapshotForm.version" placeholder="如 DS-0001" />
        </label>
        <label class="filter-item">
          <span>周期筛选（逗号分隔，留空全量）</span>
          <input v-model="snapshotForm.periodsText" placeholder="如 2026-01,2026-02" />
        </label>
        <label class="filter-item">
          <span>币种筛选（逗号分隔）</span>
          <input v-model="snapshotForm.currenciesText" placeholder="如 CNY,USD" />
        </label>
        <button class="btn primary" type="submit">生成取数快照与汇总附件</button>
      </form>
      <p class="page-desc">快照绑定数据版本、来源范围与未计入冲突项；后续导入或裁决不会改写已生成的报告。</p>
      <table class="data-table">
        <thead>
          <tr><th>快照</th><th>报告</th><th>数据版本</th><th>明细数</th><th>币种合计</th><th>未计冲突组</th><th>生成时间</th><th>附件</th></tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in snapshots" :key="snapshot.snapshot_id">
            <td>{{ snapshot.snapshot_id }}</td>
            <td>#{{ snapshot.report_id }}</td>
            <td>{{ snapshot.dataset_version }}</td>
            <td>{{ snapshot.record_count }}</td>
            <td>
              <span v-for="total in snapshot.total_by_currency" :key="total.currency" class="sum-chip">
                {{ total.currency }} {{ total.amount }}
              </span>
            </td>
            <td :class="{ 'cell-warn': snapshot.excluded_conflict_count > 0 }">
              {{ snapshot.excluded_conflict_count }}
            </td>
            <td>{{ snapshot.created_at }}</td>
            <td><button class="link" type="button" @click="downloadAttachment(snapshot.snapshot_id, snapshot.attachment_filename)">下载 CSV</button></td>
          </tr>
          <tr v-if="!snapshots.length">
            <td colspan="8" class="empty-state">暂无报告取数快照</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/business-detail'

const tabs = [
  { key: 'import', label: '明细导入' },
  { key: 'invalid', label: '无效行台账' },
  { key: 'groups', label: '归并与冲突' },
  { key: 'datasets', label: '数据集版本' },
  { key: 'snapshots', label: '报告取数快照' },
] as const

const activeTab = ref<(typeof tabs)[number]['key']>('import')
const message = ref('')
const isError = ref(false)
const uploading = ref(false)

const batches = ref<any[]>([])
const invalidRows = ref<any[]>([])
const groups = ref<any[]>([])
const datasets = ref<any[]>([])
const snapshots = ref<any[]>([])
const groupFilter = ref('')
const rawPreview = ref('')
const publishRemark = ref('')
const expandedDatasets = reactive<Record<string, boolean>>({})
const resolutionForms = reactive<Record<number, { candidateId: number | null; reason: string; operator: string }>>({})

const importForm = reactive<{ sourceName: string; datasourceId: number | null; file: File | null; content: string }>({
  sourceName: '',
  datasourceId: null,
  file: null,
  content: '',
})

const snapshotForm = reactive({
  reportId: null as number | null,
  version: '',
  periodsText: '',
  currenciesText: '',
})

function notify(text: string, error = false) {
  message.value = text
  isError.value = error
}

async function getJson(path: string) {
  const response = await request(path)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail ?? `接口返回 ${response.status}`)
  }
  return response.json()
}

async function postJson(path: string, body: Record<string, unknown>) {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail ?? `接口返回 ${response.status}`)
  }
  return payload
}

function pickFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  importForm.file = file
  importForm.content = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    importForm.content = String(reader.result ?? '')
  }
  reader.readAsText(file, 'utf-8')
}

async function submitImport() {
  if (!importForm.file || !importForm.content) {
    notify('请先选择明细文件并等待内容读取完成', true)
    return
  }
  uploading.value = true
  try {
    const payload = await postJson(`${ENDPOINT}/imports`, {
      filename: importForm.file.name,
      source_name: importForm.sourceName,
      content: importForm.content,
      datasource_id: importForm.datasourceId ?? null,
    })
    notify(payload.message)
    importForm.file = null
    importForm.content = ''
    await reloadAll()
  } catch (error) {
    notify(error instanceof Error ? error.message : '导入失败', true)
  } finally {
    uploading.value = false
  }
}

async function viewBatch(batchId: number) {
  try {
    const detail = await getJson(`${ENDPOINT}/imports/${batchId}`)
    rawPreview.value = `# 数据源：${detail.source_file.source_name} / 文件：${detail.source_file.filename}\n${detail.raw_content}`
  } catch (error) {
    notify(error instanceof Error ? error.message : '原始文件读取失败', true)
  }
}

async function loadGroups() {
  const query = groupFilter.value ? `?status=${encodeURIComponent(groupFilter.value)}` : ''
  const payload = await getJson(`${ENDPOINT}/groups${query}`)
  groups.value = payload.items
  for (const group of groups.value) {
    if (!resolutionForms[group.id]) {
      resolutionForms[group.id] = { candidateId: null, reason: '', operator: '' }
    }
  }
}

async function resolve(group: any) {
  const form = resolutionForms[group.id]
  if (!form.candidateId) {
    notify('请选择入选候选', true)
    return
  }
  try {
    const payload = await postJson(`${ENDPOINT}/groups/${group.id}/resolution`, {
      candidate_id: form.candidateId,
      reason: form.reason,
      operator: form.operator || '分析员',
    })
    notify(payload.message)
    form.reason = ''
    await loadGroups()
  } catch (error) {
    notify(error instanceof Error ? error.message : '裁决失败', true)
  }
}

async function publishCurrent() {
  try {
    const payload = await postJson(`${ENDPOINT}/datasets/publish`, { remark: publishRemark.value || null })
    notify(payload.message)
    publishRemark.value = ''
    await loadDatasets()
  } catch (error) {
    notify(error instanceof Error ? error.message : '发布失败', true)
  }
}

async function loadDatasets() {
  const payload = await getJson(`${ENDPOINT}/datasets`)
  datasets.value = payload.items
}

async function toggleDataset(version: string) {
  if (!expandedDatasets[version]) {
    const detail = await getJson(`${ENDPOINT}/datasets/${encodeURIComponent(version)}`)
    const index = datasets.value.findIndex((item) => item.version === version)
    if (index >= 0) datasets.value[index] = detail
  }
  expandedDatasets[version] = !expandedDatasets[version]
}

async function createSnapshot() {
  if (!snapshotForm.reportId) {
    notify('请填写经营分析报告 id', true)
    return
  }
  const split = (text: string) => text.split(',').map((item) => item.trim()).filter(Boolean)
  try {
    const payload = await postJson(`${ENDPOINT}/report-snapshots`, {
      report_id: snapshotForm.reportId,
      version: snapshotForm.version || null,
      periods: split(snapshotForm.periodsText),
      currencies: split(snapshotForm.currenciesText),
    })
    notify(payload.message)
    await loadSnapshots()
  } catch (error) {
    notify(error instanceof Error ? error.message : '快照生成失败', true)
  }
}

async function loadSnapshots() {
  const payload = await getJson(`${ENDPOINT}/report-snapshots`)
  snapshots.value = payload.items
}

async function downloadAttachment(snapshotId: string, filename: string) {
  try {
    const payload = await getJson(`${ENDPOINT}/report-snapshots/${snapshotId}/attachment`)
    const blob = new Blob([payload.content], { type: payload.content_type })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    notify(error instanceof Error ? error.message : '附件下载失败', true)
  }
}

const stats = ref([
  { label: '导入批次', value: 0 },
  { label: '无效行', value: 0 },
  { label: '冲突待裁决', value: 0 },
  { label: '已发布版本', value: 0 },
  { label: '报告快照', value: 0 },
])

async function reloadAll() {
  try {
    const [batchPayload, invalidPayload, datasetPayload, snapshotPayload] = await Promise.all([
      getJson(`${ENDPOINT}/imports`),
      getJson(`${ENDPOINT}/invalid-rows`),
      getJson(`${ENDPOINT}/datasets`),
      getJson(`${ENDPOINT}/report-snapshots`),
    ])
    batches.value = batchPayload.items
    invalidRows.value = invalidPayload.items
    datasets.value = datasetPayload.items
    snapshots.value = snapshotPayload.items
    await loadGroups()
    stats.value = [
      { label: '导入批次', value: batches.value.length },
      { label: '无效行', value: invalidRows.value.length },
      { label: '冲突待裁决', value: groups.value.filter((item) => item.status === '冲突').length },
      { label: '已发布版本', value: datasets.value.length },
      { label: '报告快照', value: snapshots.value.length },
    ]
  } catch (error) {
    notify(error instanceof Error ? error.message : '数据加载失败', true)
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.tab-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.tab-btn { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.tab-btn.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.notice { background: #ecfdf3; border: 1px solid #a6f4c5; color: #027a48; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.notice-error { background: #fef3f2; border-color: #fda29b; color: #b42318; }
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.import-form { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 14px; }
.file-pick { min-width: 280px; }
.grow { flex: 1; }
.wrap { flex-wrap: wrap; }
.raw-preview { background: #0b1020; color: #d1e7ff; padding: 12px; border-radius: 6px; font-size: 12px; max-height: 320px; overflow: auto; }
.cell-warn { color: #b42318; font-weight: 600; }
.group-card, .dataset-card { border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.group-card.status-冲突 { border-left: 4px solid #d92d20; }
.group-card.status-已裁决 { border-left: 4px solid #175cd3; }
.group-card.status-一致 { border-left: 4px solid #039855; }
.group-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 8px; font-size: 13px; }
.tag { background: #f2f4f7; border-radius: 999px; padding: 2px 10px; font-size: 12px; }
.tag-ok { background: #ecfdf3; color: #027a48; }
.tag-off { background: #fef3f2; color: #b42318; }
.basis { color: var(--muted); }
.inner-table { margin: 6px 0; }
.resolve-form { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-top: 8px; padding-top: 10px; border-top: 1px dashed var(--border); }
.dataset-detail { margin-top: 10px; }
.dataset-detail h4 { margin: 10px 0 6px; font-size: 13px; }
.scope-list { margin: 0; padding-left: 18px; font-size: 13px; color: var(--muted); }
.sum-chip { display: inline-block; background: #eff8ff; border: 1px solid #b2ddff; border-radius: 999px; padding: 2px 8px; margin-right: 6px; font-size: 12px; }
code { background: #f2f4f7; padding: 1px 4px; border-radius: 4px; }
</style>
