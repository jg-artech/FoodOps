<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Cobros Pendientes</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>
    <p class="text-sm text-gray-400 mb-4">
      Órdenes en efectivo entregadas por el vendedor, esperando que confirmes cuánto recibiste de verdad.
    </p>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <div v-else-if="ordenes.length === 0" class="bg-white rounded-2xl border border-gray-200 shadow-sm py-12 text-center">
      <div class="text-4xl mb-2">✅</div>
      <p class="text-gray-500">No hay cobros pendientes de confirmar.</p>
    </div>

    <div v-else class="space-y-3">
      <div v-for="orden in ordenes" :key="orden.id"
        class="bg-white rounded-2xl border border-amber-200 shadow-sm p-4">
        <div class="flex items-start justify-between mb-2">
          <div>
            <p class="font-bold text-gray-800">{{ orden.numero_orden }}</p>
            <p class="text-xs text-gray-400">{{ horaFormato(orden.created_at) }} · tomó: {{ orden.tomada_por_nombre || '—' }}</p>
          </div>
          <span class="text-xs font-bold px-2 py-1 rounded-full bg-amber-100 text-amber-700">
            PENDIENTE
          </span>
        </div>

        <p class="text-sm text-gray-600 mb-3">
          {{ orden.es_domicilio ? '🏠' : '🥡' }}
          <span class="font-medium">{{ orden.cliente_nombre || 'Para llevar' }}</span>
        </p>

        <div class="bg-gray-50 rounded-xl p-3 text-sm space-y-1 mb-3">
          <div class="flex justify-between">
            <span class="text-gray-500">Total de la orden</span>
            <span class="font-bold">Q{{ Number(orden.total).toFixed(2) }}</span>
          </div>
          <div class="flex justify-between text-gray-400 text-xs">
            <span>Estimado por el vendedor</span>
            <span>recibió Q{{ Number(orden.dinero_recibido ?? 0).toFixed(2) }}, vuelto Q{{ Number(orden.vuelto ?? 0).toFixed(2) }}</span>
          </div>
        </div>

        <button @click="abrirConfirmar(orden)"
          class="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-2.5 rounded-xl text-sm transition">
          Confirmar cobro
        </button>
      </div>
    </div>

    <p v-if="errorMsg" class="text-red-500 text-sm text-center mt-4">{{ errorMsg }}</p>

    <!-- Modal de confirmación -->
    <div v-if="ordenActiva" class="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center px-4 z-50">
      <div class="bg-white rounded-2xl p-6 max-w-sm w-full">
        <p class="font-bold text-gray-800 text-lg mb-1">{{ ordenActiva.numero_orden }}</p>
        <p class="text-sm text-gray-500 mb-4">Total: <strong>Q{{ Number(ordenActiva.total).toFixed(2) }}</strong></p>

        <label class="block text-xs text-gray-500 mb-1">¿Cuánto efectivo recibiste?</label>
        <input v-model.number="form.monto_recibido" type="number" min="0" step="0.01" autofocus
          class="w-full text-2xl font-black text-center border-2 border-gray-300 rounded-xl px-3 py-3 mb-3 focus:outline-none focus:border-orange-400" />

        <label class="block text-xs text-gray-500 mb-1">¿Cuánto vuelto entregaste?</label>
        <input v-model.number="form.vuelto_entregado" type="number" min="0" step="0.01"
          class="w-full text-xl font-bold text-center border-2 border-gray-300 rounded-xl px-3 py-2 mb-4 focus:outline-none focus:border-orange-400" />

        <p v-if="vueltoCalculadoDistinto" class="text-xs text-amber-600 mb-3 text-center">
          ⚠ El vuelto que escribiste no coincide con recibido − total (Q{{ vueltoCalculado.toFixed(2) }}). Se guarda igual tal como lo confirmes.
        </p>

        <p v-if="modalError" class="text-red-500 text-xs text-center mb-3">{{ modalError }}</p>

        <div class="flex gap-3">
          <button @click="ordenActiva = null" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl">
            Cancelar
          </button>
          <button @click="confirmarCobro" :disabled="guardando"
            class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl disabled:opacity-40">
            {{ guardando ? 'Guardando...' : 'Confirmar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const ordenes = ref([])
const loading = ref(true)
const errorMsg = ref('')

const ordenActiva = ref(null)
const modalError = ref('')
const guardando = ref(false)
const form = reactive({ monto_recibido: null, vuelto_entregado: null })

function horaFormato(fecha) {
  if (!fecha) return ''
  return new Date(fecha.replace(' ', 'T') + 'Z').toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
}

const vueltoCalculado = computed(() => {
  if (!ordenActiva.value || form.monto_recibido == null) return 0
  return form.monto_recibido - Number(ordenActiva.value.total)
})
const vueltoCalculadoDistinto = computed(() =>
  form.vuelto_entregado != null && Math.abs(form.vuelto_entregado - vueltoCalculado.value) > 0.01
)

async function cargar() {
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/ordenes/', { params: { estado_cobro: 'pendiente_recibir' } })
    ordenes.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar los cobros pendientes'
  } finally {
    loading.value = false
  }
}

function abrirConfirmar(orden) {
  ordenActiva.value = orden
  modalError.value = ''
  // Precarga con el estimado del vendedor - el responsable lo ajusta si el
  // billete real que llegó fue distinto.
  form.monto_recibido = orden.dinero_recibido ?? orden.total
  form.vuelto_entregado = orden.vuelto ?? Math.max(0, (orden.dinero_recibido ?? orden.total) - orden.total)
}

async function confirmarCobro() {
  modalError.value = ''
  if (form.monto_recibido == null || form.monto_recibido < 0 || form.vuelto_entregado == null || form.vuelto_entregado < 0) {
    modalError.value = 'Completa ambos montos'
    return
  }
  guardando.value = true
  try {
    await api.post(`/api/ordenes/${ordenActiva.value.id}/confirmar-cobro`, {
      monto_recibido: form.monto_recibido,
      vuelto_entregado: form.vuelto_entregado,
    })
    ordenes.value = ordenes.value.filter((o) => o.id !== ordenActiva.value.id)
    ordenActiva.value = null
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Error al confirmar el cobro'
  } finally {
    guardando.value = false
  }
}

onMounted(cargar)
</script>
