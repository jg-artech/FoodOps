<template>
  <div v-if="impresion.avisoMsg || impresion.errorMsg" class="text-xs space-y-1">
    <p v-if="impresion.avisoMsg" class="text-green-600">{{ impresion.avisoMsg }}</p>
    <p v-if="impresion.errorMsg" class="text-red-500">{{ impresion.errorMsg }}</p>
    <div v-if="impresion.trabajoFallido || impresion.ordenManual" class="flex flex-wrap gap-2">
      <button v-if="impresion.trabajoFallido" @click="impresion.reintentar()"
        class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-2.5 py-1 rounded-lg font-medium">
        Reintentar
      </button>
      <button v-if="impresion.ordenManual" @click="impresion.imprimirManual()"
        class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-2.5 py-1 rounded-lg font-medium">
        🖨️ Imprimir desde este equipo
      </button>
    </div>
  </div>
</template>

<script setup>
// Mensajes del flujo de ticket (ver utils/impresionTicket.js). Recibe el
// resultado de useImpresionTicket() envuelto en reactive().
defineProps({
  impresion: { type: Object, required: true },
})
</script>
