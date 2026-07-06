<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Gastos</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 mb-5">
      <label class="block text-sm font-medium text-gray-700 mb-1">Categoría</label>
      <select v-model="form.categoria" class="w-full border border-gray-300 rounded-xl px-3 py-3 mb-3 focus:outline-none focus:ring-2 focus:ring-orange-400">
        <option v-for="c in categorias" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>

      <label class="block text-sm font-medium text-gray-700 mb-1">Descripción</label>
      <input v-model="form.descripcion" type="text" maxlength="200" placeholder="Ej: Compra de arroz"
        class="w-full border border-gray-300 rounded-xl px-3 py-3 mb-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />

      <label class="block text-sm font-medium text-gray-700 mb-1">Monto</label>
      <div class="flex items-center gap-2 mb-4">
        <span class="text-lg font-bold text-gray-500">Q</span>
        <input v-model.number="form.monto" type="number" min="0" step="0.01"
          class="flex-1 text-xl font-bold border-2 border-gray-300 rounded-xl px-3 py-2 focus:outline-none focus:border-orange-400" />
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>

      <button @click="registrar" :disabled="!puedeRegistrar || submitting"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
        {{ submitting ? 'Registrando...' : 'Registrar Gasto' }}
      </button>
    </div>

    <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">Gastos de hoy</h2>
    <div v-if="loading" class="text-center py-8 text-gray-400">Cargando...</div>
    <div v-else-if="!gastos.length" class="text-center py-8 text-gray-400">Sin gastos registrados hoy.</div>
    <div v-else class="space-y-2">
      <div v-for="g in gastos" :key="g.id" class="bg-white border border-gray-200 rounded-xl p-3 flex items-center justify-between">
        <div class="min-w-0">
          <p class="font-semibold text-gray-800 text-sm truncate">{{ g.descripcion }}</p>
          <p class="text-xs text-gray-400">{{ categoriaLabel(g.categoria) }} · {{ hora(g.created_at) }}</p>
        </div>
        <span class="font-bold text-red-500 shrink-0 ml-3">Q{{ Number(g.monto).toFixed(2) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const categorias = [
  { value: 'insumos', label: 'Insumos' },
  { value: 'servicios', label: 'Servicios' },
  { value: 'sueldos', label: 'Sueldos' },
  { value: 'transporte', label: 'Transporte' },
  { value: 'publicidad', label: 'Publicidad' },
  { value: 'otros', label: 'Otros' },
]

const gastos = ref([])
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')

const form = reactive({ categoria: 'insumos', descripcion: '', monto: '' })

const puedeRegistrar = computed(() => form.descripcion.trim() && form.monto > 0)

function categoriaLabel(v) {
  return categorias.find((c) => c.value === v)?.label || v
}
function hora(iso) {
  return new Date(iso.replace(' ', 'T') + 'Z').toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
}

async function cargar() {
  loading.value = true
  try {
    const { data } = await api.get('/api/gastos')
    gastos.value = data
  } finally {
    loading.value = false
  }
}

async function registrar() {
  errorMsg.value = ''
  submitting.value = true
  try {
    await api.post('/api/gastos', { ...form })
    form.descripcion = ''
    form.monto = ''
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al registrar el gasto'
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
