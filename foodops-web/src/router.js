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
import CajaTiendaView from '@/views/CajaTiendaView.vue'
import InventarioView from '@/views/InventarioView.vue'
import GastosView from '@/views/GastosView.vue'
import DesperdiciosView from '@/views/DesperdiciosView.vue'
import FondosRepartidorView from '@/views/FondosRepartidorView.vue'
import CierreCajaView from '@/views/CierreCajaView.vue'
import StockView from '@/views/StockView.vue'
import PedidosReabastecimientoView from '@/views/PedidosReabastecimientoView.vue'
import AbastecimientoView from '@/views/AbastecimientoView.vue'
import InventarioDiarioView from '@/views/InventarioDiarioView.vue'
import ReglasReabastecimientoView from '@/views/ReglasReabastecimientoView.vue'


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
  { path: '/caja', component: CajaTiendaView, meta: { requiresAuth: true } },
  { path: '/caja/inventario/:momento', component: InventarioView, meta: { requiresAuth: true } },
  { path: '/caja/gastos', component: GastosView, meta: { requiresAuth: true } },
  { path: '/caja/desperdicios', component: DesperdiciosView, meta: { requiresAuth: true } },
  { path: '/caja/fondos-repartidor', component: FondosRepartidorView, meta: { requiresAuth: true } },
  { path: '/caja/cierre', component: CierreCajaView, meta: { requiresAuth: true } },
  { path: '/caja/stock', component: StockView, meta: { requiresAuth: true } },
  { path: '/caja/pedidos-reabastecimiento', component: PedidosReabastecimientoView, meta: { requiresAuth: true } },
  { path: '/central', redirect: '/central/abastecimiento' },
  { path: '/central/abastecimiento', component: AbastecimientoView, meta: { requiresAuth: true } },
  { path: '/central/reglas', component: ReglasReabastecimientoView, meta: { requiresAuth: true } },
  { path: '/pos/inventario-diario', component: InventarioDiarioView, meta: { requiresAuth: true } },
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
