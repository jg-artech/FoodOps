<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Fondos Repartidor</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 mb-5">
      <h2 class="font-bold text-gray-700 mb-3">Entregar fondo</h2>
      <label class="block text-sm font-medium text-gray-700 mb-1">Repartidor</label>
      <select v-model="form.repartidor_id"
        class="w-full border border-gray-300 rounded-xl px-3 py-3 mb-3 focus:outline-none focus:ring-2 focus:ring-orange-400">
        <option :value="null" disabled>Selecciona un repartidor</option>
        <option v-for="r in repartidores" :key="r.id" :value="r.id">{{ r.nombre_completo || r.username }}</option>
      </select>

      <label class="block text-sm font-medium text-gray-700 mb-1">Monto entregado</label>
      <div class="flex items-center gap-2 mb-4">
        <span class="text-lg font-bold text-gray-500">Q</span>
        <input v-model.number="form.monto_entregado" type="number" min="0" step="0.01"
          class="flex-1 text-xl font-bold border-2 border-gray-300 rounded-xl px-3 py-2 focus:outline-none focus:border-orange-400" />
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>

      <button @click="entregar" :disabled="!puedeEntregar || submitting"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
        {{ submitting ? 'Entregando...' : 'Entregar Fondo' }}
      </button>
    </div>

    <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">Fondos entregados sin liquidar</h2>
    <div v-if="loading" class="text-center py-8 text-gray-400">Cargando...</div>
    <div v-else-if="!pendientes.length" class="text-center py-8 text-gray-400">No hay fondos pendientes.</div>
    <div v-else class="space-y-2 mb-6">
      <div v-for="f in pendientes" :key="f.id" class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <p class="font-semibold text-gray-800 text-sm">{{ nombreRepartidor(f.repartidor_id) }}</p>
          <span class="font-bold text-blue-500">Q{{ Number(f.monto_entregado).toFixed(2) }}</span>
        </div>
        <div class="flex items-center gap-2">
          <input v-model.number="liquidaciones[f.id]" type="number" min="0" step="0.01" placeholder="Monto liquidado"
            class="flex-1 border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
          <button @click="liquidar(f.id)" :disabled="!liquidaciones[f.id] && liquidaciones[f.id] !== 0"
            class="bg-green-600 hover:bg-green-700 text-white font-bold px-4 py-2 rounded-lg text-sm disabled:opacity-40">
            Liquidar
          </button>
        </div>
      </div>
    </div>

    <h2 v-if="liquidados.length" class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">Liquidados hoy</h2>
    <div v-if="liquidados.length" class="space-y-2">
      <div v-for="f in liquidados" :key="f.id" class="bg-white border border-gray-200 rounded-xl p-3 flex items-center justify-between">
        <p class="font-semibold text-gray-800 text-sm">{{ nombreRepartidor(f.repartidor_id) }}</p>
        <div class="text-right">
          <p class="text-sm text-gray-500">Q{{ Number(f.monto_entregado).toFixed(2) }} → Q{{ Number(f.monto_liquidado).toFixed(2) }}</p>
          <p class="text-xs font-bold" :class="Number(f.diferencia) === 0 ? 'text-green-600' : 'text-red-500'">
            Diferencia: Q{{ Number(f.diferencia).toFixed(2) }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const repartidores = ref([])
const fondos = ref([])
const liquidaciones = reactive({})
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')

const form = reactive({ repartidor_id: null, monto_entregado: '' })

const puedeEntregar = computed(() => form.repartidor_id && form.monto_entregado > 0)
const pendientes = computed(() => fondos.value.filter((f) => f.estado !== 'liquidado'))
const liquidados = computed(() => fondos.value.filter((f) => f.estado === 'liquidado'))

function nombreRepartidor(id) {
  const r = repartidores.value.find((x) => x.id === id)
  return r?.nombre_completo || r?.username || `Usuario #${id}`
}

async function cargar() {
  loading.value = true
  try {
    const [{ data: reps }, { data: fondosData }] = await Promise.all([
      api.get('/api/auth/usuarios', { params: { rol: 'repartidor' } }),
      api.get('/api/fondos-repartidor'),
    ])
    repartidores.value = reps
    fondos.value = fondosData
  } finally {
    loading.value = false
  }
}

async function entregar() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const { data } = await api.post('/api/fondos-repartidor', { ...form })
    fondos.value.unshift(data)
    form.repartidor_id = null
    form.monto_entregado = ''
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al entregar el fondo'
  } finally {
    submitting.value = false
  }
}

async function liquidar(fondoId) {
  errorMsg.value = ''
  try {
    const { data } = await api.post(`/api/fondos-repartidor/${fondoId}/liquidar`, {
      monto_liquidado: liquidaciones[fondoId],
    })
    const idx = fondos.value.findIndex((f) => f.id === fondoId)
    if (idx !== -1) fondos.value[idx] = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al liquidar el fondo'
  }
}

onMounted(cargar)
</script>
