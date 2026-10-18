<template>
  <div>
    <div v-if="loading" class="text-center py-8 text-gray-400">Cargando órdenes...</div>
    <div v-else-if="ordenes.length === 0" class="text-center py-8 text-gray-400">No hay órdenes aún.</div>
    <div v-else class="space-y-3">
      <div
        v-for="orden in ordenes"
        :key="orden.id"
        class="bg-white rounded-lg border border-gray-200 px-4 py-3 shadow-sm"
      >
        <div class="flex items-center justify-between">
          <div>
            <p class="font-semibold text-gray-800">{{ orden.numero_orden }}</p>
            <p class="text-sm text-gray-500">{{ orden.cliente_nombre || 'Sin nombre' }}</p>
          </div>
          <div class="flex items-center gap-3">
            <div class="text-right">
              <span
                class="text-xs font-medium px-2 py-1 rounded-full"
                :class="estadoClase(orden.estado)"
              >{{ orden.estado }}</span>
              <p class="text-sm font-semibold mt-1">${{ orden.total.toFixed(2) }}</p>
            </div>
            <button
              @click="imprimir(orden)"
              :disabled="impresion.enviando"
              title="Reimprimir ticket"
              class="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-2.5 py-1.5 rounded-lg font-medium shrink-0"
            >
              🖨️
            </button>
          </div>
        </div>
        <!-- Mensajes del último ticket enviado, solo en su fila -->
        <EstadoImpresionTicket v-if="filaActiva === orden.id" :impresion="impresion" class="mt-2" />
        <HistorialImpresion :orden-id="orden.id" class="mt-1" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import EstadoImpresionTicket from '@/components/EstadoImpresionTicket.vue'
import HistorialImpresion from '@/components/HistorialImpresion.vue'
import { useImpresionTicket } from '@/utils/impresionTicket.js'

defineProps({
  ordenes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

// Un solo flujo para toda la lista; los mensajes se muestran en la fila de
// la última orden enviada.
const impresion = reactive(useImpresionTicket())
const filaActiva = ref(null)
function imprimir(orden) {
  filaActiva.value = orden.id
  impresion.imprimir(orden)
}

function estadoClase(estado) {
  return {
    pendiente: 'bg-yellow-100 text-yellow-700',
    preparando: 'bg-blue-100 text-blue-700',
    listo: 'bg-green-100 text-green-700',
    entregado: 'bg-gray-100 text-gray-600',
    cancelado: 'bg-red-100 text-red-600',
  }[estado] || 'bg-gray-100 text-gray-600'
}
</script>
