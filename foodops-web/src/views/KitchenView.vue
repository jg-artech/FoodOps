<template>
  <div class="min-h-screen bg-gray-950 text-white flex flex-col">
    <!-- Header de cocina -->
    <div class="bg-gray-900 border-b border-gray-700 px-4 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="text-xl font-black">🍗 COCINA</span>
        <span class="text-sm text-gray-400">{{ ordenes.length }} orden(es) activa(s)</span>
      </div>
      <div class="flex items-center gap-4">
        <span class="text-lg font-mono">{{ horaActual }}</span>
        <span class="flex items-center gap-1.5 text-sm" :class="conectado ? 'text-green-400' : 'text-red-400'">
          <span class="w-2 h-2 rounded-full animate-pulse" :class="conectado ? 'bg-green-400' : 'bg-red-400'"></span>
          {{ conectado ? 'En línea' : 'Sin conexión' }}
        </span>
        <RouterLink to="/pos" class="text-xs bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded-full transition">
          ← Salir
        </RouterLink>
      </div>
    </div>

    <!-- Leyenda de colores -->
    <div class="flex gap-4 text-xs px-4 py-2 bg-gray-900 border-b border-gray-800 text-gray-500">
      <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-gray-800 border border-gray-600"></span> &lt;15 min</span>
      <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-orange-800 border border-orange-400"></span> 15-30 min</span>
      <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-red-900 border border-red-500"></span> +30 min</span>
    </div>

    <!-- Comandas -->
    <div class="flex-1 p-4">
      <div v-if="ordenes.length === 0" class="flex flex-col items-center justify-center h-64 text-gray-600">
        <p class="text-6xl mb-4">😴</p>
        <p class="text-xl font-semibold">Sin órdenes pendientes</p>
        <p class="text-sm mt-1">Actualizando cada 2 segundos...</p>
      </div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <KitchenTicket
          v-for="orden in ordenes"
          :key="orden.id"
          :orden="orden"
          @cambiar="cambiarEstado"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/store/index'
import KitchenTicket from '@/components/KitchenTicket.vue'
import api from '@/services/api'

const auth = useAuthStore()
const ordenes = ref([])
const conectado = ref(true)
const horaActual = ref('')
let prevIds = new Set()
let pollTimer = null
let clockTimer = null

function playBell() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.5, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7)
    osc.start()
    osc.stop(ctx.currentTime + 0.7)
  } catch {}
}

function actualizarHora() {
  horaActual.value = new Date().toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function fetchOrdenes() {
  const puntoId = auth.puntoId
  if (!puntoId) return
  try {
    const { data } = await api.get(`/api/ordenes/${puntoId}`)
    const activas = data.filter(o => ['pendiente', 'preparando'].includes(o.estado))
    // Ordenar: más antigua primero (FIFO)
    activas.sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    const currentIds = new Set(activas.map(o => o.id))
    if (prevIds.size > 0 && [...currentIds].some(id => !prevIds.has(id))) playBell()
    prevIds = currentIds
    ordenes.value = activas
    conectado.value = true
  } catch {
    conectado.value = false
  }
}

async function cambiarEstado(orden, nuevoEstado) {
  if (nuevoEstado === 'cancelado' && !confirm(`¿Cancelar orden ${orden.numero_orden}?`)) return
  try {
    await api.put(`/api/ordenes/${orden.id}/status`, { estado: nuevoEstado })
    ordenes.value = ordenes.value.filter(o => o.id !== orden.id)
    prevIds.delete(orden.id)
  } catch (e) {
    alert(e.response?.data?.detail || 'Error al actualizar')
  }
}

onMounted(() => {
  actualizarHora()
  clockTimer = setInterval(actualizarHora, 1000)
  fetchOrdenes()
  pollTimer = setInterval(fetchOrdenes, 2000)
})
onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(clockTimer)
})
</script>
