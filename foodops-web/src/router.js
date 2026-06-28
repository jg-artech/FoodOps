import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import DashboardView from '@/views/DashboardView.vue'
import OrdenesView from '@/views/OrdenesView.vue'
import POSMainView from '@/views/POSMainView.vue'
import NewOrderView from '@/views/NewOrderView.vue'
import OrdersListView from '@/views/OrdersListView.vue'
import DayClosureView from '@/views/DayClosureView.vue'
import ConfigView from '@/views/ConfigView.vue'
import KitchenView from '@/views/KitchenView.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: LoginView },
  { path: '/dashboard', component: DashboardView, meta: { requiresAuth: true } },
  { path: '/ordenes', component: OrdenesView, meta: { requiresAuth: true } },
  { path: '/pos', component: POSMainView, meta: { requiresAuth: true } },
  { path: '/pos/nueva-orden', component: NewOrderView, meta: { requiresAuth: true } },
  { path: '/pos/ordenes', component: OrdersListView, meta: { requiresAuth: true } },
  { path: '/pos/cierre', component: DayClosureView, meta: { requiresAuth: true } },
  { path: '/pos/config', component: ConfigView, meta: { requiresAuth: true } },
  { path: '/cocina', component: KitchenView, meta: { requiresAuth: true, noNav: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) return next('/login')
  if (to.path === '/login' && token) return next('/dashboard')
  next()
})

export default router
