<template>
  <div class="max-w-4xl mx-auto px-4 py-8">
    <div v-if="isOffline" class="mb-4 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2 text-sm text-yellow-700">
      Sin conexión — mostrando órdenes guardadas localmente.
    </div>

    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Órdenes</h1>
      <button
        @click="showForm = !showForm"
        :disabled="isOffline"
        class="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-lg text-sm transition disabled:opacity-50"
      >
        {{ showForm ? 'Ver listado' : '+ Nueva Orden' }}
      </button>
    </div>

    <div v-if="showForm" class="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
      <h2 class="font-semibold text-gray-700 mb-4">Nueva Orden</h2>
      <OrdenForm @created="onOrdenCreada" @cancel="showForm = false" />
    </div>

    <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <OrdenList :ordenes="ordenes" :loading="loading" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/index'
import OrdenForm from '@/components/OrdenForm.vue'
import OrdenList from '@/components/OrdenList.vue'
import api from '@/services/api'

const CACHE_KEY = 'foodops_ordenes'

const auth = useAuthStore()
const ordenes = ref([])
const loading = ref(false)
const showForm = ref(false)
const isOffline = ref(!navigator.onLine)

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

function onOrdenCreada(nuevaOrden) {
  ordenes.value.unshift(nuevaOrden)
  localStorage.setItem(CACHE_KEY, JSON.stringify(ordenes.value))
  showForm.value = false
}

onMounted(() => {
  window.addEventListener('online', () => { isOffline.value = false; fetchOrdenes() })
  window.addEventListener('offline', () => { isOffline.value = true })
  fetchOrdenes()
})
</script>
