<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Cierre del día</h1>
      <RouterLink to="/pos" class="text-sm text-gray-500 hover:text-gray-700">← POS</RouterLink>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Calculando reporte...</div>

    <div v-else-if="reporte" class="space-y-4">
      <!-- Encabezado naranja -->
      <div class="bg-orange-500 text-white rounded-2xl p-5 shadow">
        <p class="text-sm opacity-80">Cierre del día</p>
        <p class="text-xl font-bold">{{ reporte.fecha }}</p>
        <div class="flex flex-wrap gap-6 mt-3">
          <div>
            <p class="text-3xl font-black">{{ reporte.total_ordenes }}</p>
            <p class="text-xs opacity-80">órdenes</p>
          </div>
          <div>
            <p class="text-3xl font-black">Q{{ reporte.total_dinero.toFixed(2) }}</p>
            <p class="text-xs opacity-80">ventas</p>
          </div>
          <div v-if="reporte.total_ordenes > 0">
            <p class="text-3xl font-black">Q{{ (reporte.total_dinero / reporte.total_ordenes).toFixed(2) }}</p>
            <p class="text-xs opacity-80">promedio/orden</p>
          </div>
        </div>
      </div>

      <!-- Rentabilidad (solo si hay costos registrados) -->
      <div v-if="rentabilidad && rentabilidad.tiene_costos"
        class="bg-white rounded-2xl border border-green-200 shadow-sm p-5">
        <h3 class="font-bold text-gray-700 mb-4">📊 Rentabilidad del día</h3>
        <div class="grid grid-cols-2 gap-4 mb-4">
          <div class="bg-gray-50 rounded-xl p-3 text-center">
            <p class="text-xs text-gray-500 mb-1">Ventas totales</p>
            <p class="text-xl font-black text-gray-800">Q{{ rentabilidad.total_venta.toFixed(2) }}</p>
          </div>
          <div class="bg-gray-50 rounded-xl p-3 text-center">
            <p class="text-xs text-gray-500 mb-1">Costo total</p>
            <p class="text-xl font-black text-red-500">Q{{ rentabilidad.total_costo.toFixed(2) }}</p>
          </div>
          <div class="bg-green-50 rounded-xl p-3 text-center col-span-2">
            <p class="text-xs text-green-700 mb-1">Ganancia neta</p>
            <p class="text-3xl font-black text-green-600">Q{{ rentabilidad.margen_total.toFixed(2) }}</p>
          </div>
        </div>
        <!-- Barra de margen -->
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-500 w-14 shrink-0">Margen</span>
          <div class="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full rounded-full transition-all"
              :class="rentabilidad.margen_promedio_pct >= 50 ? 'bg-green-500' : rentabilidad.margen_promedio_pct >= 30 ? 'bg-yellow-400' : 'bg-red-400'"
              :style="{ width: rentabilidad.margen_promedio_pct + '%' }"></div>
          </div>
          <span class="text-sm font-bold w-12 text-right"
            :class="rentabilidad.margen_promedio_pct >= 50 ? 'text-green-600' : 'text-yellow-600'">
            {{ rentabilidad.margen_promedio_pct }}%
          </span>
        </div>
      </div>

      <!-- Banner cuando no hay costos -->
      <div v-else-if="rentabilidad && !rentabilidad.tiene_costos"
        class="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-800">
        <p class="font-bold mb-1">💡 Activa el análisis de rentabilidad</p>
        <p>Define los costos de tus productos en <RouterLink to="/pos/config" class="underline font-semibold">Configuración → Costos</RouterLink> para ver cuánto ganas en cada venta.</p>
      </div>

      <!-- Métodos de pago -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
        <h3 class="font-bold text-gray-700 mb-3">💳 Método de pago</h3>
        <div class="space-y-3 mb-4">
          <div v-for="m in metodosDisplay" :key="m.key" class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span>{{ m.emoji }}</span>
              <span class="text-sm text-gray-600">{{ m.label }}</span>
            </div>
            <div class="flex items-center gap-3">
              <div class="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div class="h-full bg-orange-400 rounded-full transition-all"
                  :style="{ width: porcentaje(m.key) + '%' }"></div>
              </div>
              <span class="text-sm font-bold w-20 text-right">Q{{ (reporte.por_metodo_pago[m.key] || 0).toFixed(2) }}</span>
              <span class="text-xs text-gray-400 w-8 text-right">{{ porcentaje(m.key) }}%</span>
            </div>
          </div>
        </div>

      </div>

      <!-- Top productos -->
      <div v-if="topProductos.length" class="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
        <h3 class="font-bold text-gray-700 mb-3">🏆 Top productos</h3>
        <div class="space-y-2">
          <div v-for="(item, i) in topProductos" :key="item.producto" class="flex items-center gap-3">
            <span class="w-6 h-6 rounded-full bg-orange-100 text-orange-600 text-xs font-bold flex items-center justify-center shrink-0">
              {{ i + 1 }}
            </span>
            <span class="flex-1 text-sm text-gray-700">{{ item.producto }}</span>
            <span class="font-bold text-orange-500 text-sm">{{ item.cantidad }}</span>
            <span class="text-xs text-gray-400">uds</span>
          </div>
        </div>
      </div>

      <button @click="imprimir"
        class="w-full border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50 transition">
        🖨️ Imprimir reporte
      </button>
    </div>

    <div v-else class="text-center py-12 text-gray-400">No se pudo cargar el reporte.</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/store/index'
import api from '@/services/api'

const auth = useAuthStore()
const reporte = ref(null)
const rentabilidad = ref(null)
const loading = ref(false)

const metodosDisplay = [
  { key: 'efectivo',      label: 'Efectivo',      emoji: '💵' },
  { key: 'tarjeta',       label: 'Tarjeta',        emoji: '💳' },
  { key: 'transferencia', label: 'Transferencia',  emoji: '📱' },
]

const topProductos = computed(() => {
  // Fusiona top_productos del reporte estándar con el de rentabilidad
  if (rentabilidad.value?.top_productos?.length) return rentabilidad.value.top_productos.slice(0, 10)
  return reporte.value?.top_productos || []
})

function porcentaje(key) {
  if (!reporte.value?.total_dinero || reporte.value.total_dinero === 0) return 0
  return Math.round(((reporte.value.por_metodo_pago[key] || 0) / reporte.value.total_dinero) * 100)
}

async function fetchReporte() {
  const puntoId = auth.puntoId
  if (!puntoId) return
  loading.value = true
  try {
    const [r, rent] = await Promise.allSettled([
      api.get(`/api/ordenes/reporte/${puntoId}`),
      api.get(`/api/ordenes/reporte-rentabilidad/${puntoId}`),
    ])
    if (r.status === 'fulfilled') reporte.value = r.value.data
    if (rent.status === 'fulfilled') rentabilidad.value = rent.value.data
  } finally {
    loading.value = false
  }
}

function imprimir() { window.print() }

onMounted(fetchReporte)
</script>
