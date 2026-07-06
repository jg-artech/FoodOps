<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Caja y Tienda</h1>
      <RouterLink to="/dashboard" class="text-sm text-gray-500 hover:text-gray-700">← Dashboard</RouterLink>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <!-- No hay caja hoy: formulario de apertura -->
    <div v-else-if="!caja" class="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <p class="text-gray-600 mb-4">Aún no se ha abierto la caja de hoy.</p>
      <label class="block text-sm font-medium text-gray-700 mb-1">Fondo inicial</label>
      <div class="flex items-center gap-2 mb-4">
        <span class="text-lg font-bold text-gray-500">Q</span>
        <input v-model.number="fondoInicial" type="number" min="0" step="0.01"
          class="flex-1 text-2xl font-bold border-2 border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:border-orange-400" />
      </div>
      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>
      <button @click="abrirCaja" :disabled="!fondoInicial || fondoInicial < 0 || submitting"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-4 rounded-xl text-lg transition disabled:opacity-40">
        📂 {{ submitting ? 'Abriendo...' : 'Abrir Caja' }}
      </button>
    </div>

    <!-- Caja abierta o cerrada -->
    <div v-else class="space-y-4">
      <div class="rounded-2xl p-5 shadow text-white" :class="caja.estado === 'abierta' ? 'bg-orange-500' : 'bg-gray-500'">
        <p class="text-sm opacity-80">Caja de hoy — {{ caja.estado === 'abierta' ? 'Abierta' : 'Cerrada' }}</p>
        <p class="text-3xl font-black">Q{{ Number(caja.fondo_inicial).toFixed(2) }}</p>
        <p class="text-xs opacity-80">fondo inicial</p>
        <div v-if="caja.estado !== 'abierta'" class="mt-3 pt-3 border-t border-white/30 flex justify-between text-sm">
          <span>Descuadre</span>
          <span class="font-bold">Q{{ Number(caja.descuadre ?? 0).toFixed(2) }}</span>
        </div>
      </div>

      <div v-if="actual" class="grid grid-cols-2 gap-3">
        <div class="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <p class="text-xs text-gray-400 mb-1">Gastos hoy</p>
          <p class="text-xl font-bold text-red-500">Q{{ Number(actual.gastos_hoy).toFixed(2) }}</p>
        </div>
        <div class="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <p class="text-xs text-gray-400 mb-1">Fondos sin liquidar</p>
          <p class="text-xl font-bold text-blue-500">Q{{ Number(actual.fondos_entregados).toFixed(2) }}</p>
        </div>
      </div>

      <div v-if="caja.estado === 'abierta'" class="grid grid-cols-2 gap-3">
        <RouterLink to="/caja/gastos" class="bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm hover:border-orange-300">
          <div class="text-3xl mb-1">💰</div>
          <div class="font-bold text-gray-700 text-sm">Registrar Gasto</div>
        </RouterLink>
        <RouterLink to="/caja/desperdicios" class="bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm hover:border-orange-300">
          <div class="text-3xl mb-1">🗑️</div>
          <div class="font-bold text-gray-700 text-sm">Desperdicio</div>
        </RouterLink>
        <RouterLink to="/caja/fondos-repartidor" class="bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm hover:border-orange-300">
          <div class="text-3xl mb-1">🚚</div>
          <div class="font-bold text-gray-700 text-sm">Fondos Repartidor</div>
        </RouterLink>
        <RouterLink to="/caja/inventario/cierre" class="bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm hover:border-orange-300">
          <div class="text-3xl mb-1">📝</div>
          <div class="font-bold text-gray-700 text-sm">Inventario</div>
        </RouterLink>
        <RouterLink to="/caja/cierre" class="col-span-2 bg-green-600 hover:bg-green-700 text-white rounded-2xl p-5 text-center shadow-sm font-bold text-lg">
          ✅ CERRAR CAJA
        </RouterLink>
      </div>

      <RouterLink v-else to="/caja/cierre" class="block bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm hover:border-orange-300">
        <div class="font-bold text-gray-700">Ver reporte de cierre →</div>
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/services/api'

const caja = ref(null)
const actual = ref(null)
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')
const fondoInicial = ref('')

async function cargar() {
  loading.value = true
  try {
    const { data } = await api.get('/api/caja/actual')
    actual.value = data
    caja.value = data
  } catch (e) {
    if (e.response?.status === 404) {
      caja.value = null
    }
  } finally {
    loading.value = false
  }
}

async function abrirCaja() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const { data } = await api.post('/api/caja/abrir', { fondo_inicial: fondoInicial.value })
    caja.value = data
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al abrir la caja'
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
