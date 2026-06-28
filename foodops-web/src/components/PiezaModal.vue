<template>
  <div class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-2xl w-full max-w-sm shadow-2xl">
      <div class="p-6 border-b border-gray-100">
        <h3 class="text-xl font-bold text-gray-800">🍗 Seleccionar pieza</h3>
        <p class="text-gray-500 text-sm mt-1">¼ Pollo — Q{{ precio }}</p>
      </div>

      <div class="p-4 space-y-2">
        <button
          v-for="opcion in opciones"
          :key="opcion"
          @click="seleccionada = opcion"
          class="w-full p-4 border-2 rounded-xl text-left font-semibold text-base transition-all"
          :class="seleccionada === opcion
            ? 'border-orange-500 bg-orange-50 text-orange-700'
            : 'border-gray-200 text-gray-700 hover:border-orange-300 hover:bg-orange-50'"
        >
          🍗 {{ opcion }}
        </button>
      </div>

      <div class="flex gap-3 p-4 pt-2">
        <button @click="$emit('cancelar')"
          class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50 transition">
          Cancelar
        </button>
        <button @click="confirmar" :disabled="!seleccionada"
          class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
          Confirmar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  opciones: { type: Array, required: true },
  precio: { type: Number, default: 0 },
})
const emit = defineEmits(['confirmar', 'cancelar'])

const seleccionada = ref('')

function confirmar() {
  if (!seleccionada.value) return
  emit('confirmar', seleccionada.value)
  seleccionada.value = ''
}
</script>
