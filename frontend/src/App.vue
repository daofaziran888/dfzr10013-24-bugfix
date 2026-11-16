<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">企业经营分析决策平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向企业高层管理的经营分析决策平台。覆盖经营指标看板、财务多维分析、销售漏斗洞察、客户画像构建、供应链效率监控、人力效能评估、经营预测模型、异常预警与决策建议推送的完整企业分析链路。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "经营指标看板", path: "/kpi" }, { label: "财务多维分析", path: "/finance" }, { label: "销售漏斗洞察", path: "/sales" }, { label: "客户画像构建", path: "/customer" }, { label: "供应链效率监控", path: "/supply" }, { label: "人力效能评估", path: "/hr" }, { label: "经营预测模型", path: "/forecast" }, { label: "异常预警中心", path: "/alert" }, { label: "决策建议推送", path: "/decision" }, { label: "多维下钻分析", path: "/drill" }, { label: "经营分析报告", path: "/report" }, { label: "同期对比分析", path: "/compare" }, { label: "分析数据接入", path: "/datasource" }, { label: "多源经营明细导入", path: "/business-detail" }, { label: "分析缓存管理", path: "/cache" }, { label: "分析模板库", path: "/template" }, { label: "数据刷新调度", path: "/refresh" }]
</script>
