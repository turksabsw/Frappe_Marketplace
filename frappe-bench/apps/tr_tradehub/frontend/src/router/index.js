import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Layout — YENİ KONUM
import AppLayout from '@/layouts/AppLayout.vue'

// Views (lazy-loaded) — YENİ KONUMLAR
const LoginView = () => import('@/views/auth/LoginView.vue')
const DashboardView = () => import('@/views/dashboard/DashboardView.vue')
const ProductAddView = () => import('@/views/products/ProductAddView.vue')
const DocTypeListView = () => import('@/views/doctype/DocTypeListView.vue')

// Dashboard Module Pages (lazy-loaded)
const PlatformOverview = () => import('@/views/dashboard/PlatformOverview.vue')
const OrdersDashboard = () => import('@/views/dashboard/OrdersDashboard.vue')
const PaymentsDashboard = () => import('@/views/dashboard/PaymentsDashboard.vue')
const SellersDashboard = () => import('@/views/dashboard/SellersDashboard.vue')
const CatalogDashboard = () => import('@/views/dashboard/CatalogDashboard.vue')
const LogisticsDashboard = () => import('@/views/dashboard/LogisticsDashboard.vue')
const MarketingDashboard = () => import('@/views/dashboard/MarketingDashboard.vue')
const ComplianceDashboard = () => import('@/views/dashboard/ComplianceDashboard.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { guest: true },
  },
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: PlatformOverview,
        meta: { title: 'Genel Bakış', breadcrumb: 'Genel Bakış' },
      },
      {
        path: 'dashboard/orders',
        name: 'OrdersDashboard',
        component: OrdersDashboard,
        meta: { title: 'Sipariş Dashboard', breadcrumb: 'Siparişler' },
      },
      {
        path: 'dashboard/payments',
        name: 'PaymentsDashboard',
        component: PaymentsDashboard,
        meta: { title: 'Ödeme Dashboard', breadcrumb: 'Ödemeler' },
      },
      {
        path: 'dashboard/sellers',
        name: 'SellersDashboard',
        component: SellersDashboard,
        meta: { title: 'Satıcı Dashboard', breadcrumb: 'Satıcılar' },
      },
      {
        path: 'dashboard/catalog',
        name: 'CatalogDashboard',
        component: CatalogDashboard,
        meta: { title: 'Katalog Dashboard', breadcrumb: 'Katalog' },
      },
      {
        path: 'dashboard/logistics',
        name: 'LogisticsDashboard',
        component: LogisticsDashboard,
        meta: { title: 'Lojistik Dashboard', breadcrumb: 'Lojistik' },
      },
      {
        path: 'dashboard/marketing',
        name: 'MarketingDashboard',
        component: MarketingDashboard,
        meta: { title: 'Pazarlama Dashboard', breadcrumb: 'Pazarlama' },
      },
      {
        path: 'dashboard/compliance',
        name: 'ComplianceDashboard',
        component: ComplianceDashboard,
        meta: { title: 'Uyumluluk Dashboard', breadcrumb: 'Uyumluluk' },
      },
      {
        path: 'app/product-add',
        name: 'ProductAdd',
        component: ProductAddView,
        meta: { title: 'Yeni Ürün Ekle', breadcrumb: 'Yeni Ürün Ekle' },
      },
      {
        path: 'app/:doctype',
        name: 'DocTypeList',
        component: DocTypeListView,
        meta: { title: 'Liste', breadcrumb: 'Liste' },
      },
      {
        path: 'app/:doctype/:name',
        name: 'DocTypeForm',
        component: () => import('@/views/doctype/DocTypeFormView.vue'),
        meta: { title: 'Detay', breadcrumb: 'Detay' },
      },
      {
        path: 'app/report/:report',
        name: 'ReportView',
        component: DocTypeListView,
        meta: { title: 'Rapor', breadcrumb: 'Rapor' },
      },
      {
        path: 'messaging/:tab?',
        name: 'Messaging',
        component: DashboardView,
        meta: { title: 'Mesajlar', breadcrumb: 'Mesajlar' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  if (!auth.isAuthenticated && !to.meta.guest) {
    try { await auth.fetchUser() } catch { }
  }
  if (!to.meta.guest && !auth.isAuthenticated) {
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return next('/dashboard')
  }
  next()
})

export default router
