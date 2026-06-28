<template>
  <div class="max-w-4xl mx-auto px-4 py-8">
    <div v-if="isOffline" class="mb-4 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2 text-sm text-yellow-700">
      Sin conexión — mostrando datos guardados localmente.
    </div>

    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">Dashboard</h1>
        <p class="text-gray-500 text-sm mt-0.5">Bienvenido, <strong>{{ auth.user?.username }}</strong></p>
      </div>
      <RouterLink
        to="/ordenes"
        class="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition"
      >
        Nueva Orden
      </RouterLink>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
      <div class="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
        <p class="text-3xl font-bold text-orange-500">{{ ordenes.length }}</p>
        <p class="text-gray-500 text-sm mt-1">Órdenes hoy</p>
      </div>
      <div class="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
        <p class="text-3xl font-bold text-green-500">{{ ordenesActivas }}</p>
        <p class="text-gray-500 text-sm mt-1">En preparación</p>
      </div>
      <div class="bg-white rounded-xl border border-gray-200 p-5 shadow-sm text-center">
        <p class="text-3xl font-bold text-gray-700">${{ totalVentas.toFixed(2) }}</p>
        <p class="text-gray-500 text-sm mt-1">Total ventas</p>
      </div>
    </div>

    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h2 class="font-semibold text-gray-700 mb-4">Órdenes recientes</h2>
      <OrdenList :ordenes="ordenes.slice(0, 5)" :loading="loading" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/store/index'
import OrdenList from '@/components/OrdenList.vue'
import api from '@/services/api'

const CACHE_KEY = 'foodops_ordenes'

const auth = useAuthStore()
const ordenes = ref([])
const loading = ref(false)
const isOffline = ref(!navigator.onLine)

const ordenesActivas = computed(() =>
  ordenes.value.filter(o => ['pendiente', 'preparando'].includes(o.estado)).length
)
const totalVentas = computed(() =>
  ordenes.value.reduce((acc, o) => acc + o.total, 0)
)

async function fetchOrdenes() {
  const puntoId = auth.puntoId
  if (!puntoId) return
  loading.value = true
  try {
    const { data } = await api.get(`/api/ordenes/${puntoId}`)
    ordenes.value = data
    localStorage.setItem(CACHE_KEY, JSON.stringify(data))
  } catch {
    const cached = localStorage.getItem(CACHE_KEY)
    if (cached) ordenes.value = JSON.parse(cached)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('online', () => { isOffline.value = false; fetchOrdenes() })
  window.addEventListener('offline', () => { isOffline.value = true })
  fetchOrdenes()
})
</script>
