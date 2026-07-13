<template>
  <div class="rounded-2xl border-2 flex flex-col" :class="ticketBg">
    <!-- Header -->
    <div class="flex items-start justify-between p-4 pb-2">
      <div>
        <p class="font-bold text-xl">{{ orden.numero_orden }}</p>
        <p class="text-sm opacity-75">{{ horaFormato }} · hace {{ minutos }} min</p>
      </div>
      <span class="text-sm font-bold px-3 py-1 rounded-full bg-black/20">
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
            <span class="font-semibold text-base leading-snug">{{ desglosar(item.producto).base }}</span>
          </div>
          <div v-if="desglosar(item.producto).extras.length" class="ml-6 mt-1 flex flex-wrap gap-1">
            <span v-for="(ex, i) in desglosar(item.producto).extras" :key="'ex' + i"
              class="text-xs font-medium bg-white/10 border border-white/20 rounded-full px-2 py-0.5">
              🧂 {{ ex }}
            </span>
          </div>
          <div v-if="fijosDe(item.producto).length" class="ml-6 mt-1 flex flex-wrap gap-1">
            <span v-for="(fj, i) in fijosDe(item.producto)" :key="'fj' + i"
              class="text-xs font-medium bg-white/5 border border-white/10 opacity-80 rounded-full px-2 py-0.5">
              ✓ {{ fj }}
            </span>
          </div>
          <p v-else-if="!desglosar(item.producto).extras.length && getContenido(item.producto)"
            class="text-xs opacity-70 ml-6 mt-0.5 leading-relaxed border-l-2 border-white/20 pl-2">
            {{ getContenido(item.producto) }}
          </p>
        </li>
      </ul>
    </div>

    <!-- Cliente -->
    <div class="px-4 py-2 border-t border-white/20 text-sm">
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

const props = defineProps({
  orden: { type: Object, required: true },
  // producto_menu_id -> componentes[] (item_id, nombre, elegible, ...), tal como
  // lo devuelve GET /api/productos-menu. Trae la receta completa, no solo lo que
  // el cliente eligió (que ya viene embebido en item.producto).
  recetas: { type: Object, default: () => ({}) },
})
defineEmits(['cambiar'])

const menuItems = getMenu()

function getContenido(nombreProducto) {
  const found = menuItems.find(m => nombreProducto === m.nombre || nombreProducto.startsWith(m.nombre))
  return found?.contenido || null
}

// Componentes FIJOS (elegible=false) de la receta real del producto — el pollo,
// las salsas, el jalapeño, la Pepsi, etc. que nunca aparecen en item.producto
// porque no son una elección del cliente, pero cocina/empaque igual necesita
// verlos para preparar la orden completa.
const cacheFijos = new Map()
function fijosDe(nombreCompleto) {
  const base = desglosar(nombreCompleto).base
  if (cacheFijos.has(base)) return cacheFijos.get(base)
  const menuItem = menuItems.find((m) => base === m.nombre)
  const receta = menuItem ? props.recetas[menuItem.id] : null
  if (!receta) return [] // recetas aún no cargó (o no existe) - no memorizar, reintentar en el próximo render
  const resultado = receta.filter((c) => !c.elegible).map((c) => c.nombre)
  cacheFijos.set(base, resultado)
  return resultado
}

// NewOrderView arma item.producto como "Nombre base (pieza, 2x Arroz con Verduras
// (porción), Ensalada Rusa (porción))". Lo separamos aquí para mostrar el nombre
// del producto y cada elección como una etiqueta aparte, en vez de un párrafo
// corrido. Los "(porción)"/"(unidad)" de cada item de inventario se recortan por
// ser ruido para cocina (ya se entiende que es una porción).
const cacheDesglose = new Map()
function desglosar(nombreCompleto) {
  if (cacheDesglose.has(nombreCompleto)) return cacheDesglose.get(nombreCompleto)
  const match = nombreCompleto.match(/^(.+?)\s\((.+)\)$/s)
  const resultado = match
    ? {
        base: match[1],
        extras: match[2].split(', ').map((ex) => ex.replace(/\s*\([^)]*\)\s*$/, '').trim()),
      }
    : { base: nombreCompleto, extras: [] }
  cacheDesglose.set(nombreCompleto, resultado)
  return resultado
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
