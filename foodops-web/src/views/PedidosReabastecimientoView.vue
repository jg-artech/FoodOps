<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-800">Pedidos de Reabastecimiento</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <!-- Pestañas por estado -->
    <div class="flex gap-2 mb-4">
      <button v-for="tab in tabs" :key="tab.value" @click="estadoActivo = tab.value; cargar()"
        class="px-3 py-2 rounded-xl text-sm font-semibold border-2 transition-all"
        :class="estadoActivo === tab.value ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-500'">
        {{ tab.label }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>
    <div v-else-if="!pedidos.length" class="text-center py-12 text-gray-400">Sin pedidos {{ estadoActivoLabel }}.</div>

    <div v-else class="space-y-3">
      <div v-for="p in pedidos" :key="p.id" class="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
        <div class="flex items-center justify-between mb-2">
          <p class="font-bold text-gray-800">Pedido #{{ p.id }}</p>
          <span class="text-xs font-bold uppercase px-2 py-1 rounded-full" :class="badgeClase(p.estado)">{{ p.estado }}</span>
        </div>
        <p class="text-xs text-gray-400 mb-3">{{ fecha(p.created_at) }} · {{ p.tipo }}</p>

        <div class="space-y-1 mb-3">
          <div v-for="it in p.items" :key="it.id" class="flex justify-between text-sm">
            <span class="text-gray-600">{{ it.nombre }}</span>
            <span class="font-semibold text-gray-700">
              {{ it.cantidad_recibida !== null ? `${it.cantidad_solicitada} → ${it.cantidad_recibida}` : it.cantidad_solicitada }}
            </span>
          </div>
        </div>

        <div class="flex gap-2">
          <button v-if="p.estado === 'pendiente' && esGerencia" @click="confirmar(p.id)"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-semibold py-2 rounded-lg text-sm">
            Confirmar
          </button>
          <button v-if="p.estado === 'pendiente' || p.estado === 'confirmado'" @click="abrirRecibir(p)"
            class="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-2 rounded-lg text-sm">
            Recibir
          </button>
        </div>
      </div>
    </div>

    <!-- Modal recibir -->
    <div v-if="recibiendo" class="fixed inset-0 bg-black/50 flex items-center justify-center px-4 z-50">
      <div class="bg-white rounded-2xl p-6 max-w-sm w-full">
        <p class="font-bold text-gray-800 text-lg mb-4">Recibir pedido #{{ recibiendo.id }}</p>
        <div class="space-y-3 mb-4 max-h-80 overflow-y-auto">
          <div v-for="it in recibiendo.items" :key="it.id">
            <label class="block text-xs text-gray-500 mb-1">{{ it.nombre }} (solicitado: {{ it.cantidad_solicitada }})</label>
            <input v-model.number="cantidadesRecibidas[it.item_inventario_id]" type="number" min="0" step="0.01"
              class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
        </div>
        <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>
        <div class="flex gap-3">
          <button @click="recibiendo = null" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl">Cancelar</button>
          <button @click="confirmarRecepcion" :disabled="submitting" class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl disabled:opacity-40">
            {{ submitting ? 'Guardando...' : 'Confirmar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/store/index'
import api from '@/services/api'

const auth = useAuthStore()
const esGerencia = computed(() => ['gerente_general', 'admin'].includes(auth.user?.rol))

const tabs = [
  { value: 'pendiente', label: 'Pendientes' },
  { value: 'confirmado', label: 'Confirmados' },
  { value: 'entregado', label: 'Entregados' },
]

const estadoActivo = ref('pendiente')
const estadoActivoLabel = computed(() => tabs.find((t) => t.value === estadoActivo.value)?.label.toLowerCase())
const pedidos = ref([])
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')
const recibiendo = ref(null)
const cantidadesRecibidas = reactive({})

function badgeClase(estado) {
  return {
    pendiente: 'bg-amber-100 text-amber-700',
    confirmado: 'bg-blue-100 text-blue-700',
    entregado: 'bg-green-100 text-green-700',
    cancelado: 'bg-gray-100 text-gray-500',
  }[estado] || 'bg-gray-100 text-gray-500'
}

function fecha(iso) {
  return new Date(iso.replace(' ', 'T') + 'Z').toLocaleString('es-GT', { dateStyle: 'short', timeStyle: 'short' })
}

async function cargar() {
  loading.value = true
  try {
    const { data } = await api.get('/api/pedidos-reabastecimiento', { params: { estado: estadoActivo.value } })
    pedidos.value = data
  } finally {
    loading.value = false
  }
}

async function confirmar(pedidoId) {
  try {
    await api.post(`/api/pedidos-reabastecimiento/${pedidoId}/confirmar`)
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al confirmar el pedido'
  }
}

function abrirRecibir(pedido) {
  Object.keys(cantidadesRecibidas).forEach((k) => delete cantidadesRecibidas[k])
  for (const it of pedido.items) cantidadesRecibidas[it.item_inventario_id] = Number(it.cantidad_solicitada)
  recibiendo.value = pedido
  errorMsg.value = ''
}

async function confirmarRecepcion() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const items_recibidos = Object.entries(cantidadesRecibidas).map(([item_id, cantidad]) => ({
      item_id: Number(item_id),
      cantidad: Number(cantidad),
    }))
    await api.post(`/api/pedidos-reabastecimiento/${recibiendo.value.id}/recibir`, { items_recibidos })
    recibiendo.value = null
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al recibir el pedido'
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
