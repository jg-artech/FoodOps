<template>
  <div class="rounded-2xl border-2 flex flex-col" :class="ticketBg">
    <!-- Header -->
    <div class="flex items-start justify-between p-4 pb-2">
      <div>
        <p class="font-bold text-xl">{{ orden.numero_orden }}</p>
        <p class="text-sm opacity-75">{{ horaFormato }} · hace {{ minutos }} min</p>
      </div>
      <span class="text-sm font-bold px-3 py-1 rounded-full bg-black bg-opacity-20">
        {{ minutos }}m
      </span>
    </div>

    <!-- Items con contenido de combos -->
    <div class="px-4 py-2 flex-1">
      <p class="text-xs font-bold uppercase tracking-wider opacity-60 mb-2">Productos</p>
      <ul class="space-y-2">
        <li v-for="item in orden.items" :key="item.producto">
          <div class="flex gap-2 items-start">
            <span class="font-black text-lg leading-tight shrink-0">{{ item.cantidad }}×</span>
            <span class="font-semibold text-base leading-snug">{{ item.producto }}</span>
          </div>
          <p v-if="getContenido(item.producto)"
            class="text-xs opacity-70 ml-6 mt-0.5 leading-relaxed border-l-2 border-white border-opacity-20 pl-2">
            {{ getContenido(item.producto) }}
          </p>
        </li>
      </ul>
    </div>

    <!-- Cliente -->
    <div class="px-4 py-2 border-t border-white border-opacity-20 text-sm">
      <p>
        <span v-if="orden.es_domicilio">🏠 Domicilio — <strong>{{ orden.cliente_nombre }}</strong></span>
        <span v-else>🥡 Para llevar</span>
      </p>
      <p v-if="orden.cliente_telefono" class="opacity-70 text-xs mt-0.5">📱 {{ orden.cliente_telefono }}</p>
      <p v-if="orden.cliente_direccion" class="opacity-70 text-xs">📍 {{ orden.cliente_direccion }}</p>
    </div>

    <!-- ⚠️ Requerimientos especiales — DESTACADOS -->
    <div v-if="orden.notas_especiales"
      class="mx-3 mb-3 bg-yellow-300 text-yellow-900 rounded-xl p-3">
      <p class="font-black text-sm uppercase tracking-wide mb-1">⚠️ ESPECIALES</p>
      <p class="text-sm font-semibold leading-snug">{{ orden.notas_especiales }}</p>
    </div>

    <!-- Acciones -->
    <div class="flex gap-2 p-3 pt-0">
      <button @click="$emit('cambiar', orden, 'listo')"
        class="flex-1 bg-green-400 hover:bg-green-300 text-green-900 font-black py-3 rounded-xl text-lg transition">
        ✓ LISTO
      </button>
      <button @click="$emit('cambiar', orden, 'cancelado')"
        class="bg-red-500 hover:bg-red-400 text-white font-black px-4 py-3 rounded-xl transition">
        ✕
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getMenu } from '@/data/menu.js'

const props = defineProps({ orden: { type: Object, required: true } })
defineEmits(['cambiar'])

const menuItems = getMenu()

function getContenido(nombreProducto) {
  const found = menuItems.find(m => nombreProducto === m.nombre || nombreProducto.startsWith(m.nombre))
  return found?.contenido || null
}

// El backend guarda en UTC sin 'Z' — agregamos 'Z' para parsear correctamente
function parseUtc(str) {
  if (!str) return null
  return new Date(str.replace(' ', 'T') + 'Z')
}

const minutos = computed(() => {
  const d = parseUtc(props.orden.created_at)
  if (!d) return 0
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000))
})

const horaFormato = computed(() => {
  const d = parseUtc(props.orden.created_at)
  if (!d) return ''
  return d.toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
})

const ticketBg = computed(() => {
  const m = minutos.value
  if (m > 30) return 'bg-red-900 border-red-500 text-white'
  if (m > 15) return 'bg-orange-800 border-orange-400 text-white'
  return 'bg-gray-800 border-gray-600 text-white'
})
</script>
