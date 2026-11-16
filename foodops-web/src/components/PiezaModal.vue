<template>
  <!-- Mismo criterio que SelectorComponentesModal: centrado, máx. 90dvh,
       cuerpo con scroll y botones fijos. No se cierra al tocar fuera; solo
       con ✕, Cancelar o Escape. -->
  <div class="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-3"
    role="dialog" aria-modal="true" aria-label="Seleccionar pieza">
    <div class="caja-modal bg-white rounded-2xl w-full shadow-2xl flex flex-col">
      <div class="flex items-center justify-between gap-2 pl-5 pr-2 py-2 border-b border-gray-100 shrink-0">
        <div class="min-w-0">
          <h3 class="text-xl font-bold text-gray-800 leading-tight">🍗 Seleccionar pieza</h3>
          <p class="text-gray-500 text-sm">{{ nombre }} — {{ formatQ(precio) }}</p>
        </div>
        <button type="button" @click="$emit('cancelar')" aria-label="Cerrar"
          class="shrink-0 w-11 h-11 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 text-2xl leading-none">✕</button>
      </div>

      <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 space-y-2">
        <button
          v-for="opcion in opciones"
          :key="opcion"
          type="button"
          @click="seleccionada = opcion"
          class="w-full min-h-11 px-4 py-3 border-2 rounded-xl text-left font-semibold text-base transition-all"
          :class="seleccionada === opcion
            ? 'border-orange-500 bg-orange-50 text-orange-700'
            : 'border-gray-200 text-gray-700 hover:border-orange-300 hover:bg-orange-50'"
        >
          🍗 {{ opcion }}
        </button>
      </div>

      <div class="flex gap-3 px-4 py-3 border-t border-gray-100 shrink-0">
        <button type="button" @click="$emit('cancelar')"
          class="flex-1 min-h-11 border border-gray-300 text-gray-600 font-semibold rounded-xl hover:bg-gray-50 transition">
          Cancelar
        </button>
        <button type="button" @click="confirmar" :disabled="!seleccionada"
          class="flex-1 min-h-11 bg-orange-500 hover:bg-orange-600 text-white font-bold rounded-xl transition disabled:opacity-40">
          Confirmar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { formatQ } from '@/utils/moneda.js'
import { ref, onMounted, onUnmounted } from 'vue'

defineProps({
  opciones: { type: Array, required: true },
  precio: { type: Number, default: 0 },
  nombre: { type: String, default: '¼ Pollo' },
})
const emit = defineEmits(['confirmar', 'cancelar'])

const seleccionada = ref('')

function confirmar() {
  if (!seleccionada.value) return
  emit('confirmar', seleccionada.value)
  seleccionada.value = ''
}

// Escape cierra igual que ✕ / Cancelar.
function onKeydown(e) {
  if (e.key === 'Escape') emit('cancelar')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
/* Más angosto que el de personalizar (solo lleva 2-3 opciones). */
.caja-modal { max-width: 384px; max-height: 90vh; max-height: 90dvh; }
</style>
