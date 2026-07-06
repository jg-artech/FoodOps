<template>
  <div class="max-w-4xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-800">Órdenes de hoy</h1>
      <RouterLink to="/pos/nueva-orden" class="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition">
        + Nueva Orden
      </RouterLink>
    </div>

    <!-- Búsqueda -->
    <input v-model="busqueda" type="text" placeholder="Buscar por cliente o número..."
      class="w-full border border-gray-300 rounded-lg px-3 py-2 mb-4 focus:outline-none focus:ring-2 focus:ring-orange-400 text-sm" />

    <!-- Tabs -->
    <div class="flex gap-2 mb-4 overflow-x-auto pb-1">
      <button v-for="tab in tabs" :key="tab.value" @click="tabActivo = tab.value"
        class="px-4 py-2 rounded-full text-sm font-semibold whitespace-nowrap transition"
        :class="tabActivo === tab.value ? 'bg-orange-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
        {{ tab.label }}
        <span class="ml-1 bg-white bg-opacity-30 rounded-full px-1.5 text-xs">{{ conteo(tab.value) }}</span>
      </button>
    </div>

    <!-- Lista -->
    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>
    <div v-else-if="ordenesFiltradas.length === 0" class="text-center py-12 text-gray-400">
      No hay órdenes {{ tabActivo !== 'todas' ? `en estado "${tabActivo}"` : '' }}.
    </div>
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <OrderCard v-for="orden in ordenesFiltradas" :key="orden.id" :orden="orden">
        <template #acciones>
          <button v-if="orden.estado === 'pendiente'"
            @click="cambiarEstado(orden, 'preparando')"
            class="text-xs bg-blue-500 hover:bg-blue-600 text-white px-2 py-1 rounded font-medium">
            En prep.
          </button>
          <button v-if="orden.estado === 'preparando'"
            @click="cambiarEstado(orden, 'listo')"
            class="text-xs bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded font-medium">
            Listo
          </button>
          <button v-if="orden.estado === 'listo'"
            @click="cambiarEstado(orden, 'entregado')"
            class="text-xs bg-gray-500 hover:bg-gray-600 text-white px-2 py-1 rounded font-medium">
            Entregado
          </button>
          <button v-if="['pendiente','preparando'].includes(orden.estado)"
            @click="cambiarEstado(orden, 'cancelado')"
            class="text-xs bg-red-100 hover:bg-red-200 text-red-600 px-2 py-1 rounded font-medium">
            ✕
          </button>
        </template>
      </OrderCard>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/store/index'
import OrderCard from '@/components/OrderCard.vue'
import api from '@/services/api'

const auth = useAuthStore()
const ordenes = ref([])
const loading = ref(false)
const tabActivo = ref('pendiente')
const busqueda = ref('')
let pollTimer = null

const tabs = [
  { value: 'todas', label: 'Todas' },
  { value: 'pendiente', label: 'Pendiente' },
  { value: 'preparando', label: 'Preparando' },
  { value: 'listo', label: 'Listo' },
  { value: 'entregado', label: 'Entregado' },
]

const ordenesFiltradas = computed(() => {
  let lista = tabActivo.value === 'todas' ? ordenes.value : ordenes.value.filter(o => o.estado === tabActivo.value)
  if (busqueda.value) {
    const q = busqueda.value.toLowerCase()
    lista = lista.filter(o =>
      o.numero_orden?.toLowerCase().includes(q) ||
      o.cliente_nombre?.toLowerCase().includes(q)
    )
  }
  return lista
})

function conteo(estado) {
  if (estado === 'todas') return ordenes.value.length
  return ordenes.value.filter(o => o.estado === estado).length
}

async function fetchOrdenes() {
  try {
    const { data } = await api.get('/api/ordenes/')
    ordenes.value = data
  } catch {}
}

async function cambiarEstado(orden, nuevoEstado) {
  try {
    await api.put(`/api/ordenes/${orden.id}/status`, { estado: nuevoEstado })
    orden.estado = nuevoEstado
  } catch (e) {
    alert(e.response?.data?.detail || 'Error al actualizar estado')
  }
}

onMounted(() => {
  loading.value = true
  fetchOrdenes().finally(() => loading.value = false)
  pollTimer = setInterval(fetchOrdenes, 5000)
})

onUnmounted(() => clearInterval(pollTimer))
</script>
