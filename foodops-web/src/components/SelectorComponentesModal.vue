<template>
  <div class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 p-2 sm:p-4">
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

        <hr v-if="gruposRadio.length && gruposMulti.length" class="my-4 border-gray-100" />

        <!-- Grupos de cantidad múltiple (elige N de M, repetibles, con tope máximo) -->
        <div v-for="(grupo, gi) in gruposMulti" :key="'multi-' + gi" class="mb-5">
          <p class="text-sm font-bold text-gray-700 mb-2">🧂 {{ grupo.label }} (elige {{ grupo.min }}-{{ grupo.max }}, se puede repetir):</p>
          <div class="space-y-1.5">
            <div v-for="it in grupo.items" :key="it.item_id"
              class="flex items-center justify-between gap-2 border border-gray-200 rounded-xl px-3 py-2">
              <span class="text-sm text-gray-700">{{ it.nombre }}<span class="text-gray-400"> ({{ it.unidad }})</span></span>
              <div class="flex items-center gap-2 shrink-0">
                <button type="button" @click="decrementarMulti(gi, it)" :disabled="cantidadDeItemMulti(gi, it) === 0"
                  class="w-7 h-7 rounded-full border border-gray-300 text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed leading-none">−</button>
                <span class="w-5 text-center text-sm font-semibold text-gray-700">{{ cantidadDeItemMulti(gi, it) }}</span>
                <button type="button" @click="incrementarMulti(gi, grupo, it)" :disabled="(seleccionMulti[gi] || []).length >= grupo.max"
                  class="w-7 h-7 rounded-full border border-orange-300 text-orange-600 disabled:opacity-30 disabled:cursor-not-allowed leading-none">+</button>
              </div>
            </div>
          </div>
          <p class="text-xs text-gray-400 mt-1.5">Seleccionadas: {{ (seleccionMulti[gi] || []).length }} / {{ grupo.max }}</p>
        </div>

        <hr v-if="(gruposRadio.length || gruposMulti.length) && gruposCheckbox.length" class="my-4 border-gray-100" />

        <!-- Opcionales (checkbox simple) -->
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
  // grupos: [{ label, items: [{item_id, nombre, unidad, cantidad}], min, max }]
  // max === 1 && items.length > 1 -> radio (elige exactamente 1)
  // max === 1 && items.length === 1 -> checkbox opcional único
  // max > 1 -> checkboxes múltiples, tope max, mínimo min al confirmar
  grupos: { type: Array, required: true },
  fijos: { type: Array, default: () => [] },
})
const emit = defineEmits(['confirmar', 'cancelar'])

const gruposRadio = computed(() => props.grupos.filter((g) => (g.max ?? 1) === 1 && g.items.length > 1))
const gruposCheckbox = computed(() => props.grupos.filter((g) => (g.max ?? 1) === 1 && g.items.length === 1).map((g) => g.items[0]))
const gruposMulti = computed(() => props.grupos.filter((g) => (g.max ?? 1) > 1))

const seleccionRadio = reactive({})
const seleccionCheckbox = reactive({})
const seleccionMulti = reactive({})

function inicializar() {
  gruposRadio.value.forEach((g, gi) => {
    seleccionRadio[gi] = g.items[0]?.item_id ?? null
  })
  gruposCheckbox.value.forEach((it) => {
    seleccionCheckbox[it.item_id] = true // opcionales vienen marcados por defecto
  })
  gruposMulti.value.forEach((g, gi) => {
    seleccionMulti[gi] = []
  })
}
watch(() => props.grupos, inicializar, { immediate: true })

// A diferencia de gruposRadio/gruposCheckbox, seleccionMulti[gi] es una lista
// que puede tener el mismo item_id repetido (p.ej. 2x Arroz) - cada repetición
// cuenta contra el máximo del grupo igual que una opción distinta.
function cantidadDeItemMulti(gi, item) {
  return (seleccionMulti[gi] || []).filter((it) => it.item_id === item.item_id).length
}

function incrementarMulti(gi, grupo, item) {
  const actuales = seleccionMulti[gi] || []
  if (actuales.length >= grupo.max) {
    alert(`${grupo.label}: máximo ${grupo.max} opciones`)
    return
  }
  seleccionMulti[gi] = [...actuales, item]
}

function decrementarMulti(gi, item) {
  const actuales = seleccionMulti[gi] || []
  const idx = actuales.findIndex((it) => it.item_id === item.item_id)
  if (idx === -1) return
  const copia = [...actuales]
  copia.splice(idx, 1)
  seleccionMulti[gi] = copia
}

function confirmar() {
  const seleccionados = []
  gruposRadio.value.forEach((g, gi) => {
    const elegido = g.items.find((it) => it.item_id === seleccionRadio[gi])
    if (elegido) seleccionados.push(elegido)
  })
  gruposCheckbox.value.forEach((it) => {
    if (seleccionCheckbox[it.item_id]) seleccionados.push(it)
  })
  for (const [gi, grupo] of gruposMulti.value.entries()) {
    const elegidos = seleccionMulti[gi] || []
    if (elegidos.length < grupo.min) {
      alert(`${grupo.label}: debes elegir mín. ${grupo.min} opción(es)`)
      return
    }
    seleccionados.push(...elegidos)
  }
  emit('confirmar', seleccionados)
}
</script>
