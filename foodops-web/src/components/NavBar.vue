<template>
  <nav class="bg-orange-500 text-white px-6 py-3 flex items-center justify-between shadow" style="min-height:5rem">
    <div class="flex flex-col items-center">
      <img src="/Logo.png" alt="Logo" class="h-14 w-auto object-contain" />
      <span class="font-bold text-white text-sm tracking-wide leading-none">FoodOps</span>
    </div>
    <div class="flex items-center gap-4 text-sm">
      <RouterLink to="/dashboard" class="hover:underline">Dashboard</RouterLink>
      <RouterLink to="/pos" class="hover:underline">POS</RouterLink>
      <RouterLink to="/ordenes" class="hover:underline">Órdenes</RouterLink>
      <RouterLink to="/caja" class="hover:underline">Caja</RouterLink>
      <RouterLink to="/pos/inventario-diario" class="hover:underline">📦 Inventario</RouterLink>
      <RouterLink v-if="esGerenteCentral" to="/central/abastecimiento" class="hover:underline">🚚 Abastecimiento</RouterLink>
      <RouterLink v-if="esGerenteGeneral" to="/central/reglas" class="hover:underline">⚙️ Reglas Abastecimiento</RouterLink>
      <RouterLink to="/cocina" target="_blank" class="hover:underline">Cocina</RouterLink>
      <span class="opacity-80">{{ auth.user?.username }}</span>
      <button @click="handleLogout" class="bg-white text-orange-500 px-3 py-1 rounded font-medium hover:bg-orange-50">
        Salir
      </button>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/store/index'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

// auth.user.rol viene del JWT en minúsculas (ver TokenData/UserRol.value en el
// backend), no en mayúsculas - GERENTE_CENTRAL como string literal nunca
// matchearía.
const esGerenteCentral = computed(() => auth.user?.rol === 'gerente_central')
// Solo gerente_general/admin pueden crear/editar/eliminar reglas (ver
// _ROLES_GERENCIA en router_abastecimiento.py) - gerente_central puede leerlas
// pero no se le muestra este link porque los botones de guardar/eliminar le
// devolverían 403.
const esGerenteGeneral = computed(() => ['gerente_general', 'admin'].includes(auth.user?.rol))

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
