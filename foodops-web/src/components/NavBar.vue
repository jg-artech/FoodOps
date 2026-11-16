<template>
  <nav class="bg-orange-500 text-white shadow">
    <div class="h-14 min-[1440px]:h-20 px-3 min-[1440px]:px-6 flex items-center gap-3">
      <!-- Hamburguesa: solo por debajo de 1440px (ver nota en el script) -->
      <button
        type="button"
        class="min-[1440px]:hidden relative shrink-0 w-11 h-11 -ml-1 flex items-center justify-center rounded-lg hover:bg-white/15"
        aria-label="Abrir menú"
        :aria-expanded="menuAbierto"
        @click="menuAbierto = true"
      >
        <svg viewBox="0 0 24 24" class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
        <span v-if="cobrosPendientes > 0"
          class="absolute top-0.5 right-0.5 min-w-5 h-5 px-1 bg-white text-orange-600 text-xs font-bold rounded-full flex items-center justify-center">
          {{ cobrosPendientes }}
        </span>
      </button>

      <RouterLink :to="rutaInicio(auth.user)" class="shrink-0">
        <img src="/Logo.png" alt="Asados a la Leña" class="logo" />
      </RouterLink>

      <!-- Enlaces en escritorio -->
      <div class="hidden min-[1440px]:flex items-center gap-3 text-sm whitespace-nowrap">
        <RouterLink v-for="e in enlaces" :key="e.to" :to="e.to" :target="e.target" class="hover:underline">
          {{ e.label }}
          <span v-if="e.badge" class="ml-1 bg-white text-orange-600 text-xs font-bold rounded-full px-1.5 py-0.5">{{ e.badge }}</span>
        </RouterLink>
      </div>

      <!-- Siempre visible, en una sola línea -->
      <div class="ml-auto flex items-center gap-3 min-w-0 text-sm whitespace-nowrap">
        <SelectorTienda />
        <button @click="handleLogout" :title="'Cerrar sesión de ' + (auth.user?.username || '')"
          class="hidden min-[1440px]:inline-block bg-white text-orange-500 px-3 py-1 rounded font-medium hover:bg-orange-50">
          Salir
        </button>
      </div>
    </div>

    <!-- Panel a pantalla completa (por debajo de 1440px) -->
    <div v-if="menuAbierto" class="min-[1440px]:hidden fixed inset-0 z-50 bg-orange-500 text-white flex flex-col"
      role="dialog" aria-modal="true" aria-label="Menú">
      <div class="h-14 px-3 flex items-center gap-3 border-b border-white/20 shrink-0">
        <button type="button" class="w-11 h-11 -ml-1 flex items-center justify-center rounded-lg hover:bg-white/15 text-2xl"
          aria-label="Cerrar menú" @click="menuAbierto = false">✕</button>
        <img src="/Logo.png" alt="Asados a la Leña" class="logo" />
        <span class="ml-auto opacity-80 text-sm whitespace-nowrap truncate">{{ auth.user?.username }}</span>
      </div>
      <div class="flex-1 overflow-y-auto overscroll-contain py-2">
        <RouterLink v-for="e in enlaces" :key="e.to" :to="e.to" :target="e.target"
          class="flex items-center gap-2 min-h-12 px-5 text-lg font-medium hover:bg-white/10 active:bg-white/20"
          active-class="bg-white/15"
          @click="menuAbierto = false">
          {{ e.label }}
          <span v-if="e.badge" class="ml-auto bg-white text-orange-600 text-sm font-bold rounded-full px-2 py-0.5">{{ e.badge }}</span>
        </RouterLink>
      </div>
      <div class="p-4 border-t border-white/20 shrink-0">
        <button @click="handleLogout"
          class="w-full min-h-12 bg-white text-orange-600 rounded-xl font-bold text-lg hover:bg-orange-50">
          Salir
        </button>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import SelectorTienda from '@/components/SelectorTienda.vue'
import { useAuthStore } from '@/store/index'
import { useRoute, useRouter } from 'vue-router'
import api from '@/services/api'
import { ROLES_CONFIRMAR_COBRO, ROLES_GERENCIA, ROLES_SOLO_POS, rutaInicio, tieneRol } from '@/permisos.js'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

// auth.user.rol viene del JWT en minúsculas (ver TokenData/UserRol.value en el
// backend), no en mayúsculas - GERENTE_CENTRAL como string literal nunca
// matchearía.
const esGerenteCentral = computed(() => auth.user?.rol === 'gerente_central')
// Solo gerente_general/admin pueden crear/editar/eliminar reglas (ver
// _ROLES_GERENCIA en router_abastecimiento.py) - gerente_central puede leerlas
// pero no se le muestra este link porque los botones de guardar/eliminar le
// devolverían 403.
const esGerenteGeneral = computed(() => tieneRol(auth.user, ROLES_GERENCIA))
// gerente_punto sí entra aquí aunque no tenga acceso a caja/gastos/fondos
// (ROLES_CAJA, otro set distinto). Ver src/permisos.js.
const puedeConfirmarCobro = computed(() => tieneRol(auth.user, ROLES_CONFIRMAR_COBRO))

const cobrosPendientes = ref(0)
let pollCobros = null

// Una sola lista para la barra de escritorio y el panel del menú. El
// vendedor solo ve POS (el router además lo devuelve a /pos desde cualquier
// otra ruta, y el backend le responde 403 en lo demás).
const enlaces = computed(() => tieneRol(auth.user, ROLES_SOLO_POS) ? [{ to: '/pos', label: 'POS' }] : [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/pos', label: 'POS' },
  { to: '/ordenes', label: 'Órdenes' },
  { to: '/caja', label: 'Caja' },
  { to: '/pos/inventario-diario', label: '📦 Inventario' },
  esGerenteCentral.value && { to: '/central/abastecimiento', label: '🚚 Abastecimiento' },
  esGerenteGeneral.value && { to: '/central/reglas', label: '⚙️ Reglas Abastecimiento' },
  esGerenteGeneral.value && { to: '/central/puntos', label: '🏪 Puntos de Venta' },
  esGerenteGeneral.value && { to: '/admin/usuarios', label: '👥 Usuarios' },
  puedeConfirmarCobro.value && { to: '/caja/cobros-pendientes', label: '💵 Cobros', badge: cobrosPendientes.value || null },
  { to: '/cocina', label: 'Cocina', target: '_blank' },
].filter(Boolean))

// Por debajo de 1440px se usa el menú: con todos los enlaces de gerencia
// (admin), la barra completa mide ~1370px y no cabe en una línea en una
// tablet de 1024px ni en una laptop de 1366px.
const menuAbierto = ref(false)
watch(() => route.fullPath, () => { menuAbierto.value = false })
watch(menuAbierto, (abierto) => {
  document.body.style.overflow = abierto ? 'hidden' : ''
})
function onKeydown(e) {
  if (e.key === 'Escape' && menuAbierto.value) menuAbierto.value = false
}

async function cargarCobrosPendientes() {
  if (!puedeConfirmarCobro.value) return
  try {
    const { data } = await api.get('/api/ordenes/', { params: { estado_cobro: 'pendiente_recibir' } })
    cobrosPendientes.value = data.length
  } catch {
    // Silencioso: es solo el contador del menú, no bloquea nada.
  }
}

function handleLogout() {
  menuAbierto.value = false
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  cargarCobrosPendientes()
  pollCobros = setInterval(cargarCobrosPendientes, 20000)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  clearInterval(pollCobros)
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
/* 40px en pantallas pequeñas, 56px en escritorio (mismo corte que el menú) */
.logo { height: 40px; width: auto; object-fit: contain; }
@media (min-width: 1440px) { .logo { height: 56px; } }
</style>
