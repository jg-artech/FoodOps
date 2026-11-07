<template>
  <div class="border border-gray-200 rounded-2xl p-4 bg-white">
    <label class="flex items-center justify-between gap-3 cursor-pointer">
      <span class="font-semibold text-gray-700">🧾 ¿Requiere factura?</span>
      <input v-model="datos.requiere_factura" type="checkbox" :disabled="disabled"
        class="w-5 h-5 accent-orange-500" />
    </label>

    <div v-if="datos.requiere_factura" class="space-y-3 mt-3">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">NIT *</label>
        <input v-model="datos.nit" type="text" placeholder="1234567-8" autocomplete="off"
          :maxlength="NIT_MAX + 5" :disabled="disabled" @blur="datos.nit = normalizarNit(datos.nit)"
          class="w-full border rounded-xl px-3 py-2.5 uppercase focus:outline-none focus:ring-2 focus:ring-orange-400"
          :class="nitConError ? 'border-red-400' : 'border-gray-300'" />
        <p v-if="nitConError" class="text-red-500 text-xs mt-1">{{ MSG_NIT_INVALIDO }}</p>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Nombre fiscal *</label>
        <input v-model="datos.nombre_fiscal" type="text" placeholder="Como aparece en el NIT" autocomplete="off"
          maxlength="200" :disabled="disabled"
          class="w-full border border-gray-300 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-orange-400" />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Dirección fiscal *</label>
        <input v-model="datos.direccion_fiscal" type="text" placeholder="Ciudad" autocomplete="off"
          maxlength="255" :disabled="disabled"
          class="w-full border border-gray-300 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-orange-400" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { MSG_NIT_INVALIDO, NIT_MAX, NIT_REGEX, normalizarNit } from '@/utils/factura.js'

// `datos` es un objeto reactive del padre ({ requiere_factura, nit,
// nombre_fiscal, direccion_fiscal }); este componente edita sus campos.
const props = defineProps({
  datos: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
})

// Solo marca el NIT en rojo cuando ya se escribió algo con mal formato;
// el "falta el NIT" lo muestra el padre junto al botón.
const nitConError = computed(() => {
  const nit = normalizarNit(props.datos.nit)
  return nit !== '' && (nit.length > NIT_MAX || !NIT_REGEX.test(nit))
})
</script>
