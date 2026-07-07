<template>
  <div class="fixed inset-0 bg-black bg-opacity-60 flex items-end sm:items-center justify-center z-50 p-2 sm:p-4">
    <div class="bg-white rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
        <div>
          <p class="font-bold text-gray-800 text-lg">Personalizar: {{ nombre }}</p>
          <p class="text-xs text-gray-400 mt-0.5">Q{{ Number(precio).toFixed(2) }}</p>
        </div>
        <button @click="$emit('cancelar')" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">✕</button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 py-4">
        <!-- Grupos de radio (elige 1) -->
        <div v-for="(grupo, gi) in gruposRadio" :key="'radio-' + gi" class="mb-5">
          <p class="text-sm font-bold text-gray-700 mb-2">🧂 {{ grupo.label }} (elige 1):</p>
          <div class="space-y-1.5">
            <label v-for="it in grupo.items" :key="it.item_id"
              class="flex items-center gap-2 border rounded-xl px-3 py-2 cursor-pointer transition-all"
              :class="seleccionRadio[gi] === it.item_id ? 'border-orange-400 bg-orange-50' : 'border-gray-200'">
              <input type="radio" :name="'grupo-' + gi" :value="it.item_id" v-model="seleccionRadio[gi]" class="accent-orange-500" />
              <span class="text-sm text-gray-700">{{ it.nombre }}<span class="text-gray-400"> ({{ it.unidad }})</span></span>
            </label>
          </div>
        </div>

        <hr v-if="gruposRadio.length && gruposCheckbox.length" class="my-4 border-gray-100" />

        <!-- Opcionales (checkbox) -->
        <div v-if="gruposCheckbox.length" class="mb-5">
          <p class="text-sm font-bold text-gray-700 mb-2">📋 Opcionales:</p>
          <div class="space-y-1.5">
            <label v-for="it in gruposCheckbox" :key="it.item_id"
              class="flex items-center gap-2 border border-gray-200 rounded-xl px-3 py-2 cursor-pointer">
              <input type="checkbox" v-model="seleccionCheckbox[it.item_id]" class="w-4 h-4 accent-orange-500" />
              <span class="text-sm text-gray-700">{{ it.nombre }}<span class="text-gray-400"> ({{ it.cantidad }} {{ it.unidad }})</span></span>
            </label>
          </div>
        </div>

        <hr v-if="fijos.length" class="my-4 border-gray-100" />

        <!-- Componentes fijos (solo lectura) -->
        <div v-if="fijos.length">
          <p class="text-sm font-bold text-gray-700 mb-2">Componentes fijos:</p>
          <ul class="text-sm text-gray-500 space-y-0.5">
            <li v-for="f in fijos" :key="f.item_id">✓ {{ f.nombre }}</li>
          </ul>
        </div>
      </div>

      <!-- Acciones -->
      <div class="flex gap-3 px-5 py-4 border-t border-gray-200 shrink-0">
        <button @click="$emit('cancelar')"
          class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">
          Cancelar
        </button>
        <button @click="confirmar" class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl">
          Continuar con selección
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed, watch } from 'vue'

const props = defineProps({
  nombre: { type: String, required: true },
  precio: { type: [Number, String], default: 0 },
  // grupos: [{ label, items: [{item_id, nombre, unidad, cantidad}] }] con 2+ items -> radio
  // grupos con exactamente 1 item -> se muestran como checkbox opcional (ver agruparElegibles)
  grupos: { type: Array, required: true },
  fijos: { type: Array, default: () => [] },
})
const emit = defineEmits(['confirmar', 'cancelar'])

const gruposRadio = computed(() => props.grupos.filter((g) => g.items.length > 1))
const gruposCheckbox = computed(() => props.grupos.filter((g) => g.items.length === 1).map((g) => g.items[0]))

const seleccionRadio = reactive({})
const seleccionCheckbox = reactive({})

function inicializar() {
  gruposRadio.value.forEach((g, gi) => {
    seleccionRadio[gi] = g.items[0]?.item_id ?? null
  })
  gruposCheckbox.value.forEach((it) => {
    seleccionCheckbox[it.item_id] = true // opcionales vienen marcados por defecto
  })
}
watch(() => props.grupos, inicializar, { immediate: true })

function confirmar() {
  const seleccionados = []
  gruposRadio.value.forEach((g, gi) => {
    const elegido = g.items.find((it) => it.item_id === seleccionRadio[gi])
    if (elegido) seleccionados.push(elegido)
  })
  gruposCheckbox.value.forEach((it) => {
    if (seleccionCheckbox[it.item_id]) seleccionados.push(it)
  })
  emit('confirmar', seleccionados)
}
</script>
