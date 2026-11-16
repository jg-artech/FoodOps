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
import PuntosVentaView from '@/views/PuntosVentaView.vue'
import UsuariosView from '@/views/UsuariosView.vue'
import CobrosPendientesView from '@/views/CobrosPendientesView.vue'
import {
  ROLES_CAJA,
  ROLES_CENTRAL,
  ROLES_CONFIRMAR_COBRO,
  ROLES_GERENCIA,
  ROLES_SOLO_POS,
  RUTAS_SOLO_POS,
  rutaInicio,
} from '@/permisos.js'

// Las listas de roles son copias de las del backend (src/permisos.js). Solo
// evitan que alguien llegue a una pantalla que le devolvería 403: la
// autorización real es siempre la del backend.

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: LoginView },
  { path: '/dashboard', component: DashboardView, meta: { requiresAuth: true } },
  { path: '/ordenes', component: OrdenesView, meta: { requiresAuth: true } },
  { path: '/pos', component: POSMainView, meta: { requiresAuth: true } },
  { path: '/pos/nueva-orden', component: NewOrderView, meta: { requiresAuth: true } },
  { path: '/pos/ordenes', component: OrdersListView, meta: { requiresAuth: true } },
  { path: '/pos/cierre', component: DayClosureView, meta: { requiresAuth: true } },
  { path: '/pos/config', component: ConfigView, meta: { requiresAuth: true, roles: ROLES_GERENCIA } },
  { path: '/cocina', component: KitchenView, meta: { requiresAuth: true, noNav: true } },
  { path: '/caja', component: CajaTiendaView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/inventario/:momento', component: InventarioView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/gastos', component: GastosView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/desperdicios', component: DesperdiciosView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/fondos-repartidor', component: FondosRepartidorView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/cierre', component: CierreCajaView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/cobros-pendientes', component: CobrosPendientesView, meta: { requiresAuth: true, roles: ROLES_CONFIRMAR_COBRO } },
  { path: '/caja/stock', component: StockView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/caja/pedidos-reabastecimiento', component: PedidosReabastecimientoView, meta: { requiresAuth: true, roles: ROLES_CAJA } },
  { path: '/central', redirect: '/central/abastecimiento' },
  { path: '/central/abastecimiento', component: AbastecimientoView, meta: { requiresAuth: true, roles: ROLES_CENTRAL } },
  { path: '/central/reglas', component: ReglasReabastecimientoView, meta: { requiresAuth: true, roles: ROLES_GERENCIA } },
  { path: '/central/puntos', component: PuntosVentaView, meta: { requiresAuth: true, roles: ROLES_GERENCIA } },
  { path: '/admin/usuarios', component: UsuariosView, meta: { requiresAuth: true, roles: ROLES_GERENCIA } },
  { path: '/pos/inventario-diario', component: InventarioDiarioView, meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) return next('/login')
  const usuario = JSON.parse(localStorage.getItem('user') || 'null')
  const inicio = rutaInicio(usuario)
  if (to.path === '/login' && token) return next(inicio)
  // El vendedor solo navega por el POS: cualquier otra ruta (incluidas /,
  // /dashboard y /cocina) lo devuelve a /pos antes de montar la pantalla.
  if (token && ROLES_SOLO_POS.includes(usuario?.rol) && !RUTAS_SOLO_POS.includes(to.path)) {
    return next('/pos')
  }
  if (to.meta.roles && !to.meta.roles.includes(usuario?.rol)) return next(inicio)
  next()
})

export default router
