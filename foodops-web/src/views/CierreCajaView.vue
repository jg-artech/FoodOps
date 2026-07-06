<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Cierre de Caja</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <!-- Ya cerrada: mostrar reporte -->
    <div v-else-if="caja?.estado !== 'abierta'" class="space-y-4">
      <div class="rounded-2xl p-5 shadow text-white"
        :class="Math.abs(Number(caja.descuadre ?? 0)) <= UMBRAL ? 'bg-green-600' : 'bg-red-500'">
        <p class="text-sm opacity-80">Caja cerrada</p>
        <p class="text-3xl font-black">Q{{ Number(caja.descuadre ?? 0).toFixed(2) }}</p>
        <p class="text-xs opacity-80">descuadre</p>
      </div>
      <div class="bg-white rounded-2xl border border-gray-200 p-5 space-y-2 text-sm">
        <div class="flex justify-between"><span class="text-gray-500">Efectivo esperado</span><span class="font-bold">Q{{ Number(caja.efectivo_esperado ?? 0).toFixed(2) }}</span></div>
        <div class="flex justify-between"><span class="text-gray-500">Efectivo contado</span><span class="font-bold">Q{{ Number(caja.efectivo_contado ?? 0).toFixed(2) }}</span></div>
      </div>
      <RouterLink to="/caja" class="block w-full text-center border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
        Volver a Caja
      </RouterLink>
    </div>

    <!-- Paso 1: resumen -->
    <div v-else-if="paso === 1" class="space-y-4">
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-2 text-sm">
        <div class="flex justify-between"><span class="text-gray-500">Fondo inicial</span><span class="font-bold">Q{{ Number(caja.fondo_inicial).toFixed(2) }}</span></div>
        <div class="flex justify-between"><span class="text-gray-500">Gastos del día</span><span class="font-bold text-red-500">-Q{{ Number(actual.gastos_hoy).toFixed(2) }}</span></div>
        <div class="flex justify-between"><span class="text-gray-500">Fondos sin liquidar</span><span class="font-bold text-red-500">-Q{{ Number(actual.fondos_entregados).toFixed(2) }}</span></div>
        <hr class="my-2">
        <p class="text-xs text-amber-600">El efectivo esperado final se calcula en el backend al confirmar el cierre (incluye ventas en efectivo y liquidaciones del día).</p>
      </div>

      <div v-if="!inventarioCierreCompleto" class="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-800">
        <p class="font-bold mb-1">⚠️ Falta el conteo de inventario de cierre</p>
        <RouterLink to="/caja/inventario/cierre" class="underline font-semibold">Completar inventario →</RouterLink>
      </div>

      <button @click="paso = 2" :disabled="!inventarioCierreCompleto"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-4 rounded-xl text-lg transition disabled:opacity-40">
        Continuar al conteo →
      </button>
    </div>

    <!-- Paso 2: conteo físico -->
    <div v-else class="space-y-4">
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
        <label class="block font-bold text-gray-700 mb-3">¿Cuánto contaste en caja?</label>
        <div class="flex items-center gap-3">
          <span class="text-2xl font-bold text-gray-500">Q</span>
          <input v-model.number="efectivoContado" type="number" min="0" step="0.01" autofocus
            class="flex-1 text-3xl font-black text-center border-2 border-gray-300 rounded-xl px-4 py-3 focus:outline-none focus:border-orange-400" />
        </div>
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm text-center">{{ errorMsg }}</p>

      <div class="flex gap-3">
        <button @click="paso = 1" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
          ← Volver
        </button>
        <button @click="confirmar = true" :disabled="efectivoContado === '' || efectivoContado === null"
          class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
          CERRAR CAJA
        </button>
      </div>
    </div>

    <!-- Modal de confirmación -->
    <div v-if="confirmar" class="fixed inset-0 bg-black/50 flex items-center justify-center px-4 z-50">
      <div class="bg-white rounded-2xl p-6 max-w-sm w-full">
        <p class="font-bold text-gray-800 text-lg mb-2">¿Está seguro?</p>
        <p class="text-sm text-gray-500 mb-5">Esta acción cerrará la caja del día. Contado: <strong>Q{{ Number(efectivoContado).toFixed(2) }}</strong></p>
        <div class="flex gap-3">
          <button @click="confirmar = false" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl">Cancelar</button>
          <button @click="cerrarCaja" :disabled="submitting" class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl disabled:opacity-40">
            {{ submitting ? 'Cerrando...' : 'Confirmar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/services/api'

const UMBRAL = 10

const caja = ref(null)
const actual = ref(null)
const inventarioCierreCompleto = ref(false)
const loading = ref(true)
const submitting = ref(false)
const confirmar = ref(false)
const errorMsg = ref('')
const paso = ref(1)
const efectivoContado = ref('')

async function cargar() {
  loading.value = true
  try {
    const { data } = await api.get('/api/caja/actual')
    actual.value = data
    caja.value = data
    if (data.estado === 'abierta') {
      const { data: inv } = await api.get('/api/inventario/diario/cierre')
      inventarioCierreCompleto.value = !!inv.completado
    }
  } finally {
    loading.value = false
  }
}

async function cerrarCaja() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const { data } = await api.post('/api/caja/cerrar', { efectivo_contado: efectivoContado.value })
    caja.value = data
    confirmar.value = false
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cerrar la caja'
    confirmar.value = false
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
