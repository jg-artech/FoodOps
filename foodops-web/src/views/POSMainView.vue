<template>
  <div class="max-w-lg mx-auto px-4 py-6">
    <!-- Header con hora y stats -->
    <div class="bg-orange-500 text-white rounded-2xl p-5 mb-6 shadow">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm font-medium opacity-80">Asados a la Leña</p>
          <p class="text-2xl font-bold">{{ horaActual }}</p>
        </div>
        <div class="text-right">
          <p class="text-2xl font-bold">{{ stats.total }}</p>
          <p class="text-xs opacity-80">órdenes hoy</p>
        </div>
      </div>
      <div class="flex gap-4 mt-3 text-xs font-medium">
        <span class="bg-white bg-opacity-20 rounded-full px-3 py-1">
          🟡 {{ stats.pendiente }} pendiente
        </span>
        <span class="bg-white bg-opacity-20 rounded-full px-3 py-1">
          🔵 {{ stats.preparando }} en prep.
        </span>
        <span class="bg-white bg-opacity-20 rounded-full px-3 py-1">
          🟢 {{ stats.listo }} listo
        </span>
      </div>
    </div>

    <!-- Botones principales -->
    <div class="space-y-4">
      <RouterLink to="/pos/nueva-orden" class="pos-btn bg-orange-500 hover:bg-orange-600">
        <span class="text-4xl">🍗</span>
        <span class="text-2xl font-bold">NUEVA ORDEN</span>
      </RouterLink>

      <RouterLink to="/pos/ordenes" class="pos-btn bg-blue-500 hover:bg-blue-600">
        <span class="text-4xl">📋</span>
        <div class="text-center">
          <p class="text-2xl font-bold">VER ÓRDENES HOY</p>
          <p class="text-sm opacity-80 mt-1">
            {{ stats.pendiente }} pendiente · {{ stats.preparando }} en prep. · {{ stats.listo }} listo
          </p>
        </div>
      </RouterLink>

      <RouterLink to="/pos/cierre" class="pos-btn bg-green-600 hover:bg-green-700">
        <span class="text-4xl">💰</span>
        <div class="text-center">
          <p class="text-2xl font-bold">CIERRE DEL DÍA</p>
          <p class="text-sm opacity-80 mt-1">Total: Q{{ totalVentas.toFixed(2) }}</p>
        </div>
      </RouterLink>

      <RouterLink to="/pos/config" class="pos-btn bg-gray-600 hover:bg-gray-700">
        <span class="text-4xl">⚙️</span>
        <span class="text-2xl font-bold">CONFIGURACIÓN</span>
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/store/index'
import api from '@/services/api'

const auth = useAuthStore()
const ordenes = ref([])
const horaActual = ref('')
let clockTimer = null
let pollTimer = null

const stats = computed(() => ({
  pendiente: ordenes.value.filter(o => o.estado === 'pendiente').length,
  preparando: ordenes.value.filter(o => o.estado === 'preparando').length,
  listo: ordenes.value.filter(o => o.estado === 'listo').length,
  total: ordenes.value.length,
}))

const totalVentas = computed(() =>
  ordenes.value.filter(o => o.estado !== 'cancelado').reduce((acc, o) => acc + o.total, 0)
)

function actualizarHora() {
  horaActual.value = new Date().toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
}

async function fetchOrdenes() {
  const puntoId = auth.puntoId
  if (!puntoId) return
  try {
    const { data } = await api.get(`/api/ordenes/${puntoId}`)
    ordenes.value = data
  } catch {}
}

onMounted(() => {
  actualizarHora()
  clockTimer = setInterval(actualizarHora, 1000)
  fetchOrdenes()
  pollTimer = setInterval(fetchOrdenes, 15000)
})
onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
})
</script>

<style scoped>
.pos-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  min-height: 100px;
  border-radius: 1rem;
  color: white;
  text-decoration: none;
  transition: all 0.15s;
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.15);
  padding: 1.25rem;
}
.pos-btn:active { transform: scale(0.98); }
</style>
