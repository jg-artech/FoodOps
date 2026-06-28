<template>
  <div class="bg-white rounded-xl border-2 shadow-sm p-4 flex flex-col gap-3" :class="borderClase">
    <!-- Header -->
    <div class="flex items-start justify-between">
      <div>
        <p class="font-bold text-gray-800">{{ orden.numero_orden }}</p>
        <p class="text-xs text-gray-400">{{ horaFormato }}</p>
      </div>
      <span class="text-xs font-bold px-2 py-1 rounded-full" :class="estadoClase">
        {{ orden.estado.toUpperCase() }}
      </span>
    </div>

    <!-- Cliente -->
    <p class="text-sm text-gray-600">
      {{ orden.es_domicilio ? '🏠' : '🥡' }}
      <span class="font-medium">{{ orden.cliente_nombre || 'Para llevar' }}</span>
      <span v-if="orden.cliente_direccion" class="text-gray-400"> · {{ orden.cliente_direccion }}</span>
    </p>

    <!-- Items con contenido de combos -->
    <div v-if="orden.items?.length" class="space-y-2">
      <div v-for="item in orden.items" :key="item.producto">
        <p class="text-sm text-gray-800 font-semibold">
          <span class="text-orange-500 font-bold">{{ item.cantidad }}×</span> {{ item.producto }}
        </p>
        <p v-if="getContenido(item.producto)" class="text-xs text-gray-500 ml-4 mt-0.5 leading-relaxed">
          📦 {{ getContenido(item.producto) }}
        </p>
      </div>
    </div>

    <!-- Requerimientos especiales -->
    <div v-if="orden.notas_especiales" class="bg-amber-50 border border-amber-300 rounded-lg px-3 py-2">
      <p class="text-xs font-bold text-amber-700 mb-0.5">⚠️ Requerimientos especiales:</p>
      <p class="text-xs text-amber-900 font-medium">{{ orden.notas_especiales }}</p>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between mt-auto">
      <span class="font-bold text-orange-500">Q{{ orden.total.toFixed(2) }}</span>
      <div class="flex gap-2">
        <slot name="acciones" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getMenu } from '@/data/menu.js'

const props = defineProps({
  orden: { type: Object, required: true },
})

const menuItems = getMenu()

function getContenido(nombreProducto) {
  const found = menuItems.find(m => nombreProducto === m.nombre || nombreProducto.startsWith(m.nombre))
  return found?.contenido || null
}

const horaFormato = computed(() => {
  if (!props.orden.created_at) return ''
  return new Date(props.orden.created_at.replace(' ', 'T') + 'Z')
    .toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit' })
})

const estadoClase = computed(() => ({
  pendiente:  'bg-yellow-100 text-yellow-700',
  preparando: 'bg-blue-100 text-blue-700',
  listo:      'bg-green-100 text-green-700',
  entregado:  'bg-gray-100 text-gray-600',
  cancelado:  'bg-red-100 text-red-600',
}[props.orden.estado] || 'bg-gray-100 text-gray-600'))

const borderClase = computed(() => ({
  pendiente:  'border-yellow-300',
  preparando: 'border-blue-300',
  listo:      'border-green-300',
  entregado:  'border-gray-200',
  cancelado:  'border-red-200',
}[props.orden.estado] || 'border-gray-200'))
</script>
