<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-800">Stock en Vivo</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <!-- Selector de tienda (solo gerencia con varias tiendas) -->
    <div v-if="esGerencia && tiendas.length > 1" class="flex gap-2 mb-4 overflow-x-auto pb-1">
      <button v-for="t in tiendas" :key="t.punto.id" @click="seleccionarTienda(t.punto.id)"
        class="px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap border-2 transition-all"
        :class="puntoSeleccionado === t.punto.id ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-500'">
        {{ t.punto.nombre }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <div v-else class="space-y-4">
      <!-- Resumen -->
      <div v-if="resumen" class="grid grid-cols-2 gap-3">
        <div class="bg-red-50 border border-red-200 rounded-xl p-4 text-center">
          <p class="text-2xl font-black text-red-500">{{ resumen.items_urgentes }}</p>
          <p class="text-xs text-red-600">urgentes</p>
        </div>
        <div class="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
          <p class="text-2xl font-black text-green-600">{{ resumen.items_ok }}</p>
          <p class="text-xs text-green-700">OK</p>
        </div>
      </div>

      <!-- Tabla de stock -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th class="text-left px-3 py-2">Item</th>
                <th class="text-right px-3 py-2">Apertura</th>
                <th class="text-right px-3 py-2">Consumo</th>
                <th class="text-right px-3 py-2">Estimado</th>
                <th class="text-center px-3 py-2">Estado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in stockConEstado" :key="item.item_id" class="border-t border-gray-100">
                <td class="px-3 py-2 font-medium text-gray-800">{{ item.nombre }}</td>
                <td class="px-3 py-2 text-right text-gray-500">{{ item.cantidad_apertura }}</td>
                <td class="px-3 py-2 text-right text-gray-500">{{ item.consumo_teorico }}</td>
                <td class="px-3 py-2 text-right font-bold text-gray-800">{{ item.stock_estimado }}</td>
                <td class="px-3 py-2 text-center">
                  <span class="inline-block w-3 h-3 rounded-full" :class="colorEstado(item.estado)" :title="item.estado" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Recomendaciones (solo gerencia) -->
      <div v-if="recomendacionesUrgentes.length" class="bg-white rounded-2xl border border-red-200 shadow-sm p-5">
        <h2 class="font-bold text-red-600 mb-3">🚨 Recomendaciones de reabastecimiento</h2>
        <div class="space-y-2 mb-4">
          <label v-for="r in recomendacionesUrgentes" :key="r.item_id"
            class="flex items-center gap-3 border border-gray-200 rounded-xl p-3">
            <input type="checkbox" v-model="seleccionados[r.item_id]" class="w-5 h-5 accent-orange-500" />
            <div class="flex-1 min-w-0">
              <p class="font-semibold text-gray-800 text-sm">{{ r.nombre }}</p>
              <p class="text-xs text-gray-400">
                {{ r.dias_disponibles !== null ? `${r.dias_disponibles.toFixed(1)} días disponibles` : 'sin historial' }}
              </p>
            </div>
            <span class="font-bold text-orange-500">{{ r.cantidad_sugerida.toFixed(0) }}</span>
          </label>
        </div>
        <p v-if="errorMsg" class="text-red-500 text-sm mb-2">{{ errorMsg }}</p>
        <button @click="crearPedido" :disabled="!haySeleccionados || creandoPedido"
          class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
          {{ creandoPedido ? 'Creando...' : '+ Crear Pedido de Reabastecimiento' }}
        </button>
      </div>

      <RouterLink to="/caja/pedidos-reabastecimiento" class="block text-center border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
        📋 Ver pedidos de reabastecimiento
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/store/index'
import api from '@/services/api'

const auth = useAuthStore()
const esGerencia = computed(() => ['gerente_general', 'admin'].includes(auth.user?.rol))

const tiendas = ref([])
const puntoSeleccionado = ref(auth.puntoId)
const stock = ref([])
const recomendaciones = ref([])
const resumen = ref(null)
const seleccionados = reactive({})
const loading = ref(true)
const creandoPedido = ref(false)
const errorMsg = ref('')

function colorEstado(estado) {
  return { URGENTE: 'bg-red-500', NORMAL: 'bg-yellow-400', OK: 'bg-green-500' }[estado] || 'bg-gray-300'
}

const recomendacionPorItem = computed(() => {
  const map = {}
  for (const r of recomendaciones.value) map[r.item_id] = r
  return map
})

const stockConEstado = computed(() =>
  stock.value.map((s) => ({ ...s, estado: recomendacionPorItem.value[s.item_id]?.recomendacion || 'OK' }))
)

const recomendacionesUrgentes = computed(() => recomendaciones.value.filter((r) => r.recomendacion === 'URGENTE'))
const haySeleccionados = computed(() => Object.values(seleccionados).some(Boolean))

async function cargar() {
  loading.value = true
  errorMsg.value = ''
  try {
    if (esGerencia.value) {
      const { data: multi } = await api.get('/api/gerencia/dashboard/multi-tienda')
      tiendas.value = multi
      if (!puntoSeleccionado.value && multi.length) puntoSeleccionado.value = multi[0].punto.id

      const { data } = await api.get('/api/gerencia/dashboard', { params: { punto_id: puntoSeleccionado.value } })
      stock.value = data.stock
      recomendaciones.value = data.recomendaciones
      resumen.value = data.resumen
    } else {
      const { data } = await api.get('/api/stock/actual')
      stock.value = data
      recomendaciones.value = []
      resumen.value = null
    }
  } finally {
    loading.value = false
  }
}

async function crearPedido() {
  errorMsg.value = ''
  creandoPedido.value = true
  try {
    const items = recomendacionesUrgentes.value
      .filter((r) => seleccionados[r.item_id])
      .map((r) => ({ item_id: r.item_id, cantidad: r.cantidad_sugerida, razon: 'stock_bajo' }))
    await api.post('/api/pedidos-reabastecimiento', { tipo: 'solicitud_central', items })
    Object.keys(seleccionados).forEach((k) => delete seleccionados[k])
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al crear el pedido'
  } finally {
    creandoPedido.value = false
  }
}

function seleccionarTienda(puntoId) {
  puntoSeleccionado.value = puntoId
  cargar()
}

onMounted(cargar)
</script>
