<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Desperdicios</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 mb-5">
      <label class="block text-sm font-medium text-gray-700 mb-1">Producto</label>
      <select v-model="form.item_inventario_id" @change="onItemChange"
        class="w-full border border-gray-300 rounded-xl px-3 py-3 mb-3 focus:outline-none focus:ring-2 focus:ring-orange-400">
        <option :value="null" disabled>Selecciona un producto</option>
        <option v-for="i in items" :key="i.id" :value="i.id">{{ i.nombre }}</option>
      </select>

      <div class="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Cantidad</label>
          <input v-model.number="form.cantidad" type="number" min="0" step="0.01"
            class="w-full border border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Unidad</label>
          <input v-model="form.unidad" type="text" maxlength="20"
            class="w-full border border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />
        </div>
      </div>

      <label class="block text-sm font-medium text-gray-700 mb-1">Motivo (opcional)</label>
      <input v-model="form.motivo" type="text" maxlength="200" placeholder="Ej: se cayó, venció, se quemó"
        class="w-full border border-gray-300 rounded-xl px-3 py-3 mb-4 focus:outline-none focus:ring-2 focus:ring-orange-400" />

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>

      <button @click="registrar" :disabled="!puedeRegistrar || submitting"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
        {{ submitting ? 'Registrando...' : 'Registrar Desperdicio' }}
      </button>
    </div>

    <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">Desperdicios de hoy</h2>
    <div v-if="loading" class="text-center py-8 text-gray-400">Cargando...</div>
    <div v-else-if="!desperdicios.length" class="text-center py-8 text-gray-400">Sin desperdicios registrados hoy.</div>
    <div v-else class="space-y-2">
      <div v-for="d in desperdicios" :key="d.id" class="bg-white border border-gray-200 rounded-xl p-3 flex items-center justify-between">
        <div class="min-w-0">
          <p class="font-semibold text-gray-800 text-sm truncate">{{ nombreItem(d.item_inventario_id) }}</p>
          <p class="text-xs text-gray-400 truncate">{{ d.motivo || 'Sin motivo' }} · {{ hora(d.created_at) }}</p>
        </div>
        <div class="text-right shrink-0 ml-3">
          <p class="font-bold text-gray-700 text-sm">{{ d.cantidad }} {{ d.unidad }}</p>
          <p v-if="d.costo_estimado" class="text-xs text-red-500">Q{{ Number(d.costo_estimado).toFixed(2) }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const items = ref([])
const desperdicios = ref([])
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')

const form = reactive({ item_inventario_id: null, cantidad: '', unidad: '', motivo: '' })

const puedeRegistrar = computed(() => form.item_inventario_id && form.cantidad > 0 && form.unidad.trim())

function onItemChange() {
  const item = items.value.find((i) => i.id === form.item_inventario_id)
  if (item) form.unidad = item.unidad
}

function nombreItem(id) {
  return items.value.find((i) => i.id === id)?.nombre || '—'
}
function hora(iso) {
  return new Date(iso.replace(' ', 'T') + 'Z').toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
}

async function cargar() {
  loading.value = true
  try {
    const [{ data: itemsData }, { data: despData }] = await Promise.all([
      api.get('/api/inventario/items'),
      api.get('/api/desperdicios'),
    ])
    items.value = itemsData
    desperdicios.value = despData
  } finally {
    loading.value = false
  }
}

async function registrar() {
  errorMsg.value = ''
  submitting.value = true
  try {
    await api.post('/api/desperdicios', { ...form })
    form.item_inventario_id = null
    form.cantidad = ''
    form.unidad = ''
    form.motivo = ''
    await cargar()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al registrar el desperdicio'
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
