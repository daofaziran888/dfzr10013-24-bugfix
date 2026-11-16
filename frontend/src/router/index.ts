import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
const Kpi = () => import('@/views/kpi/index.vue')
const Finance = () => import('@/views/finance/index.vue')
const Sales = () => import('@/views/sales/index.vue')
const Customer = () => import('@/views/customer/index.vue')
const Supply = () => import('@/views/supply/index.vue')
const Hr = () => import('@/views/hr/index.vue')
const Forecast = () => import('@/views/forecast/index.vue')
const Alert = () => import('@/views/alert/index.vue')
const Decision = () => import('@/views/decision/index.vue')
const Drill = () => import('@/views/drill/index.vue')
const Report = () => import('@/views/report/index.vue')
const Compare = () => import('@/views/compare/index.vue')
const Datasource = () => import('@/views/datasource/index.vue')
const BusinessDetail = () => import('@/views/business-detail/index.vue')
const Cache = () => import('@/views/cache/index.vue')
const Template = () => import('@/views/template/index.vue')
const Refresh = () => import('@/views/refresh/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/kpi', name: 'kpi', component: Kpi },
    { path: '/finance', name: 'finance', component: Finance },
    { path: '/sales', name: 'sales', component: Sales },
    { path: '/customer', name: 'customer', component: Customer },
    { path: '/supply', name: 'supply', component: Supply },
    { path: '/hr', name: 'hr', component: Hr },
    { path: '/forecast', name: 'forecast', component: Forecast },
    { path: '/alert', name: 'alert', component: Alert },
    { path: '/decision', name: 'decision', component: Decision },
    { path: '/drill', name: 'drill', component: Drill },
    { path: '/report', name: 'report', component: Report },
    { path: '/compare', name: 'compare', component: Compare },
    { path: '/datasource', name: 'datasource', component: Datasource },
    { path: '/business-detail', name: 'business-detail', component: BusinessDetail },
    { path: '/cache', name: 'cache', component: Cache },
    { path: '/template', name: 'template', component: Template },
    { path: '/refresh', name: 'refresh', component: Refresh },
  ],
})

export default router
