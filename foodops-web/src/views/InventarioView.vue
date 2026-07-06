<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-800">Inventario — {{ tituloMomento }}</h1>
      <RouterLink to="/caja" class="text-sm text-gray-500 hover:text-gray-700">← Caja</RouterLink>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <div v-else>
      <!-- Barra de progreso -->
      <div class="bg-white rounded-xl border border-gray-200 p-3 mb-4 flex items-center gap-3">
        <div class="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
          <div class="h-full bg-orange-500 rounded-full transition-all" :style="{ width: progreso + '%' }" />
        </div>
        <span class="text-xs font-bold text-gray-500 shrink-0">{{ contados }} de {{ items.length }}</span>
      </div>

      <div class="space-y-2 mb-24">
        <div v-for="tipo in tipos" :key="tipo">
          <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mt-4 mb-2">{{ tipoLabel(tipo) }}</h3>
          <div v-for="item in itemsPorTipo(tipo)" :key="item.id"
            class="bg-white border border-gray-200 rounded-xl p-3 mb-2 flex items-center justify-between gap-3">
            <div class="flex-1 min-w-0">
              <p class="font-semibold text-gray-800 text-sm truncate">{{ item.nombre }}</p>
              <p class="text-xs text-gray-400">{{ item.unidad }}</p>
            </div>
            <input v-model.number="cantidades[item.id]" type="number" min="0" step="0.01" placeholder="0"
              class="w-24 text-lg font-bold text-center border-2 rounded-xl px-2 py-2 focus:outline-none"
              :class="cantidades[item.id] !== undefined && cantidades[item.id] !== null && cantidades[item.id] !== ''
                ? 'border-green-300 bg-green-50' : 'border-gray-200'" />
          </div>
        </div>
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3 text-center">{{ errorMsg }}</p>

      <div class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4">
        <div class="max-w-lg mx-auto">
          <button @click="completarConteo" :disabled="submitting"
            class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-4 rounded-xl text-lg transition disabled:opacity-40">
            {{ submitting ? 'Guardando...' : `✓ Completar conteo de ${tituloMomento.toLowerCase()}` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()

const momento = computed(() => (route.params.momento === 'apertura' ? 'apertura' : 'cierre'))
const tituloMomento = computed(() => (momento.value === 'apertura' ? 'Apertura' : 'Cierre'))

const items = ref([])
const cantidades = reactive({})
const loading = ref(true)
const submitting = ref(false)
const errorMsg = ref('')

const tipos = ['vendible', 'desechable', 'insumo']
function tipoLabel(t) {
  return { vendible: 'Vendibles', desechable: 'Desechables', insumo: 'Insumos' }[t] || t
}
function itemsPorTipo(t) {
  return items.value.filter((i) => i.tipo === t)
}

const contados = computed(
  () => Object.values(cantidades).filter((v) => v !== undefined && v !== null && v !== '').length
)
const progreso = computed(() => (items.value.length ? Math.round((contados.value / items.value.length) * 100) : 0))

async function cargar() {
  loading.value = true
  try {
    const [{ data: itemsData }, { data: draft }] = await Promise.all([
      api.get('/api/inventario/items'),
      api.get(`/api/inventario/diario/${momento.value}`),
    ])
    items.value = itemsData
    for (const d of draft?.detalle || []) {
      cantidades[d.item_id] = d.cantidad
    }
  } finally {
    loading.value = false
  }
}

async function completarConteo() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const payload = {
      items: Object.entries(cantidades)
        .filter(([, v]) => v !== undefined && v !== null && v !== '')
        .map(([item_id, cantidad]) => ({ item_id: Number(item_id), cantidad: Number(cantidad) })),
    }
    await api.post(`/api/inventario/diario/${momento.value}`, payload)
    router.push('/caja')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al guardar el conteo'
  } finally {
    submitting.value = false
  }
}

onMounted(cargar)
</script>
