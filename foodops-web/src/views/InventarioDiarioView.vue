<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Inventario Diario</h1>
      <RouterLink to="/pos" class="text-sm text-gray-500 hover:text-gray-700">← POS</RouterLink>
    </div>
    <p class="text-xs text-gray-400 mb-4">{{ fechaLabel }}</p>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <div v-else>
      <!-- Resumen -->
      <div class="grid grid-cols-3 gap-2 mb-4">
        <div class="bg-white border border-gray-200 rounded-xl p-3 text-center">
          <p class="text-xl font-black text-gray-700">{{ totalInicio.toFixed(0) }}</p>
          <p class="text-xs text-gray-400">Inicio</p>
        </div>
        <div class="bg-white border border-gray-200 rounded-xl p-3 text-center">
          <p class="text-xl font-black text-blue-600">{{ totalIngresa.toFixed(0) }}</p>
          <p class="text-xs text-gray-400">Ingresa</p>
        </div>
        <div class="bg-white border border-gray-200 rounded-xl p-3 text-center">
          <p class="text-xl font-black text-red-500">{{ totalConsumo.toFixed(0) }}</p>
          <p class="text-xs text-gray-400">Consumo</p>
        </div>
      </div>

      <div class="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-center">
        <p class="text-xs text-orange-600 font-semibold uppercase tracking-wide">Dato final estimado</p>
        <p class="text-2xl font-black text-orange-600">{{ totalFinal.toFixed(2) }}</p>
        <p class="text-xs text-orange-500">= Inicio + Ingresa − Consumo, por item</p>
      </div>

      <!-- Tabla por tipo -->
      <div v-for="tipo in tipos" :key="tipo" class="mb-4">
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{{ tipoLabel(tipo) }}</h3>
        <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-gray-50 text-gray-400 text-xs uppercase">
                <tr>
                  <th class="text-left px-3 py-2">Item</th>
                  <th class="text-right px-3 py-2">Inicio</th>
                  <th class="text-right px-3 py-2">Ingresa</th>
                  <th class="text-right px-3 py-2">Consumo</th>
                  <th class="text-right px-3 py-2">Final</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="it in itemsPorTipo(tipo)" :key="it.item_id" class="border-t border-gray-100">
                  <td class="px-3 py-2 font-medium text-gray-800">{{ it.nombre }}</td>
                  <td class="px-3 py-2 text-right text-gray-500">{{ it.cantidad_apertura }}</td>
                  <td class="px-3 py-2 text-right text-blue-500">{{ it.cantidad_recibida }}</td>
                  <td class="px-3 py-2 text-right text-red-400">{{ it.consumo_teorico }}</td>
                  <td class="px-3 py-2 text-right font-bold text-gray-800">{{ it.stock_estimado }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="itemsPorTipo(tipo).length === 0" class="px-3 py-4 text-center text-xs text-gray-400">
            Sin items en esta categoría
          </div>
        </div>
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm text-center mb-3">{{ errorMsg }}</p>

      <div class="grid grid-cols-2 gap-3">
        <RouterLink to="/caja/inventario/apertura" class="bg-white border border-gray-200 rounded-2xl p-4 text-center shadow-sm hover:border-orange-300">
          <div class="text-2xl mb-1">📂</div>
          <div class="font-bold text-gray-700 text-sm">Abrir inventario</div>
        </RouterLink>
        <RouterLink to="/caja/inventario/cierre" class="bg-white border border-gray-200 rounded-2xl p-4 text-center shadow-sm hover:border-orange-300">
          <div class="text-2xl mb-1">🔒</div>
          <div class="font-bold text-gray-700 text-sm">Cerrar inventario</div>
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/services/api'

const items = ref([])
const loading = ref(true)
const errorMsg = ref('')

const fechaLabel = computed(() => new Date().toLocaleDateString('es-GT', { weekday: 'long', day: 'numeric', month: 'long' }))

const tipos = ['vendible', 'insumo', 'desechable']
function tipoLabel(t) {
  return { vendible: 'Vendibles', insumo: 'Insumos', desechable: 'Desechables' }[t] || t
}
function itemsPorTipo(t) {
  return items.value.filter((i) => i.tipo === t)
}

const totalInicio = computed(() => items.value.reduce((s, i) => s + i.cantidad_apertura, 0))
const totalIngresa = computed(() => items.value.reduce((s, i) => s + i.cantidad_recibida, 0))
const totalConsumo = computed(() => items.value.reduce((s, i) => s + i.consumo_teorico, 0))
const totalFinal = computed(() => items.value.reduce((s, i) => s + i.stock_estimado, 0))

async function cargar() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/stock/actual')
    items.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar el inventario del día'
  } finally {
    loading.value = false
  }
}

onMounted(cargar)
</script>
