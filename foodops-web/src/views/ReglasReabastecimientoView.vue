<template>
  <div class="max-w-3xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Reglas de Abastecimiento</h1>
      <RouterLink to="/central/abastecimiento" class="text-sm text-gray-500 hover:text-gray-700">← Abastecimiento</RouterLink>
    </div>
    <p class="text-sm text-gray-400 mb-4">Configura mínimos, máximos y consumo esperado por item y punto de venta</p>

    <!-- Filtros -->
    <div class="flex flex-wrap gap-2 mb-4">
      <select v-model="filtro.item_id"
        class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
        <option value="">Todos los items</option>
        <option v-for="item in items" :key="item.id" :value="item.id">{{ item.nombre }}</option>
      </select>

      <select v-model="filtro.punto_id"
        class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
        <option value="">Todas las tiendas</option>
        <option v-for="punto in puntos" :key="punto.id" :value="punto.id">{{ punto.nombre }}</option>
      </select>

      <button @click="cargarReglas" class="bg-gray-700 hover:bg-gray-800 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
        Filtrar
      </button>
      <button @click="abrirModalNueva" class="ml-auto bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
        + Agregar Regla
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <!-- Tabla -->
    <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-3 py-2">Item</th>
              <th class="text-left px-3 py-2">Punto</th>
              <th class="text-right px-3 py-2">Mín</th>
              <th class="text-right px-3 py-2">Máx</th>
              <th class="text-right px-3 py-2">Consumo Base</th>
              <th class="text-right px-3 py-2">Fact. Sáb</th>
              <th class="text-right px-3 py-2">Fact. Dom</th>
              <th class="text-center px-3 py-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="regla in reglas" :key="regla.id" class="border-t border-gray-100">
              <td class="px-3 py-2 font-medium text-gray-800">{{ regla.item_nombre }}</td>
              <td class="px-3 py-2 text-gray-500">{{ regla.punto_nombre || '(todas)' }}</td>
              <td class="px-3 py-2 text-right text-gray-600">{{ regla.stock_minimo }}</td>
              <td class="px-3 py-2 text-right text-gray-600">{{ regla.stock_maximo }}</td>
              <td class="px-3 py-2 text-right text-gray-400">{{ regla.consumo_diario_base ?? '—' }}</td>
              <td class="px-3 py-2 text-right text-gray-400">{{ regla.factor_sabado }}</td>
              <td class="px-3 py-2 text-right text-gray-400">{{ regla.factor_domingo }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap">
                <button @click="editar(regla)" title="Editar" class="text-blue-500 hover:text-blue-700 px-1">✏️</button>
                <button @click="eliminar(regla.id)" title="Eliminar" class="text-red-400 hover:text-red-600 px-1">🗑️</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="reglas.length === 0" class="px-3 py-8 text-center text-sm text-gray-400">
        Sin reglas para este filtro
      </div>
    </div>

    <p v-if="errorMsg" class="text-red-500 text-sm text-center mt-3">{{ errorMsg }}</p>

    <!-- Modal crear/editar -->
    <div v-if="modalAbierto" class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 p-2 sm:p-4">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        <div class="px-5 py-4 border-b border-gray-200 shrink-0">
          <h3 class="font-bold text-gray-800">{{ modalTitulo }}</h3>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <div>
            <label class="text-xs text-gray-500 block mb-1">Item</label>
            <select v-model.number="reglaForm.item_inventario_id" :disabled="modalEditar"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 disabled:bg-gray-100 disabled:text-gray-500">
              <option :value="null" disabled>Selecciona un item</option>
              <option v-for="item in items" :key="item.id" :value="item.id">{{ item.nombre }}</option>
            </select>
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Punto (vacío = aplica a todas las tiendas)</label>
            <select v-model="reglaForm.punto_venta_id" :disabled="modalEditar"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 disabled:bg-gray-100 disabled:text-gray-500">
              <option :value="null">(Todas las tiendas)</option>
              <option v-for="punto in puntos" :key="punto.id" :value="punto.id">{{ punto.nombre }}</option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500 block mb-1">Stock Mínimo</label>
              <input v-model.number="reglaForm.stock_minimo" type="number" min="0" step="0.01"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div>
              <label class="text-xs text-gray-500 block mb-1">Stock Máximo</label>
              <input v-model.number="reglaForm.stock_maximo" type="number" min="0" step="0.01"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Consumo Diario Base (M-V)</label>
            <input v-model.number="reglaForm.consumo_diario_base" type="number" min="0" step="0.01"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500 block mb-1">Factor Sábado</label>
              <input v-model.number="reglaForm.factor_sabado" type="number" min="0" step="0.01"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div>
              <label class="text-xs text-gray-500 block mb-1">Factor Domingo</label>
              <input v-model.number="reglaForm.factor_domingo" type="number" min="0" step="0.01"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>

          <p v-if="modalError" class="text-red-500 text-xs">{{ modalError }}</p>
        </div>

        <div class="flex gap-3 px-5 py-4 border-t border-gray-200 shrink-0">
          <button @click="cerrarModal"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">Cancelar</button>
          <button @click="guardar" :disabled="guardando"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl disabled:opacity-40">
            {{ guardando ? 'Guardando...' : 'Guardar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const items = ref([])
const puntos = ref([])
const reglas = ref([])
const loading = ref(true)
const errorMsg = ref('')

const filtro = reactive({ item_id: '', punto_id: '' })

const modalAbierto = ref(false)
const modalEditar = ref(false)
const modalTitulo = computed(() => modalEditar.value ? 'Editar Regla' : 'Nueva Regla')
const modalError = ref('')
const guardando = ref(false)
const reglaEditandoId = ref(null)

function formularioVacio() {
  return {
    item_inventario_id: null,
    punto_venta_id: null,
    stock_minimo: 0,
    stock_maximo: 100,
    consumo_diario_base: 0,
    factor_sabado: 1.3,
    factor_domingo: 1.5,
  }
}
const reglaForm = reactive(formularioVacio())

async function cargarItems() {
  const { data } = await api.get('/api/inventario/items')
  items.value = data
}

async function cargarPuntos() {
  const { data } = await api.get('/api/puntos-venta')
  puntos.value = data
}

async function cargarReglas() {
  errorMsg.value = ''
  try {
    const params = {}
    if (filtro.item_id) params.item_id = filtro.item_id
    if (filtro.punto_id) params.punto_id = filtro.punto_id
    const { data } = await api.get('/api/reglas-reabastecimiento', { params })
    reglas.value = data.reglas
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar las reglas'
  }
}

function abrirModalNueva() {
  modalEditar.value = false
  modalError.value = ''
  reglaEditandoId.value = null
  Object.assign(reglaForm, formularioVacio())
  modalAbierto.value = true
}

function editar(regla) {
  modalEditar.value = true
  modalError.value = ''
  reglaEditandoId.value = regla.id
  Object.assign(reglaForm, {
    item_inventario_id: regla.item_inventario_id,
    punto_venta_id: regla.punto_venta_id,
    stock_minimo: regla.stock_minimo,
    stock_maximo: regla.stock_maximo,
    consumo_diario_base: regla.consumo_diario_base ?? 0,
    factor_sabado: regla.factor_sabado,
    factor_domingo: regla.factor_domingo,
  })
  modalAbierto.value = true
}

function cerrarModal() {
  modalAbierto.value = false
}

async function guardar() {
  modalError.value = ''
  if (!modalEditar.value && !reglaForm.item_inventario_id) {
    modalError.value = 'Selecciona un item'
    return
  }
  if (Number(reglaForm.stock_maximo) < Number(reglaForm.stock_minimo)) {
    modalError.value = 'El máximo no puede ser menor que el mínimo'
    return
  }

  guardando.value = true
  try {
    if (modalEditar.value) {
      await api.patch(`/api/reglas-reabastecimiento/${reglaEditandoId.value}`, {
        stock_minimo: reglaForm.stock_minimo,
        stock_maximo: reglaForm.stock_maximo,
        consumo_diario_base: reglaForm.consumo_diario_base,
        factor_sabado: reglaForm.factor_sabado,
        factor_domingo: reglaForm.factor_domingo,
      })
    } else {
      await api.post('/api/reglas-reabastecimiento', {
        item_inventario_id: reglaForm.item_inventario_id,
        punto_venta_id: reglaForm.punto_venta_id,
        stock_minimo: reglaForm.stock_minimo,
        stock_maximo: reglaForm.stock_maximo,
        consumo_diario_base: reglaForm.consumo_diario_base,
        factor_sabado: reglaForm.factor_sabado,
        factor_domingo: reglaForm.factor_domingo,
      })
    }
    cerrarModal()
    await cargarReglas()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Error al guardar la regla'
  } finally {
    guardando.value = false
  }
}

async function eliminar(id) {
  if (!confirm('¿Eliminar esta regla?')) return
  errorMsg.value = ''
  try {
    await api.delete(`/api/reglas-reabastecimiento/${id}`)
    await cargarReglas()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al eliminar la regla'
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([cargarItems(), cargarPuntos()])
    await cargarReglas()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar items o puntos de venta'
  } finally {
    loading.value = false
  }
})
</script>
