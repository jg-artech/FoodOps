<template>
  <div>
    <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5 text-sm text-blue-800">
      <p class="font-bold mb-1">Items de inventario</p>
      <p>
        Son los que se cuentan en el Inventario Diario, en este mismo orden dentro de cada tipo (cámbialo con ▲ ▼).
        Para que una venta descuente un item, agrégalo a la receta del producto (🧩 en la pestaña Menú).
        No se borran: se desactivan.
      </p>
    </div>

    <!-- Agregar -->
    <form @submit.prevent="agregar" class="bg-white rounded-2xl border border-dashed border-gray-300 p-5 mb-5">
      <h3 class="font-bold text-gray-500 text-sm mb-3">+ Nuevo item</h3>
      <div class="flex flex-wrap gap-2">
        <input v-model="nuevo.nombre" maxlength="100" placeholder="Nombre (ej: Mirinda 1.75L)" autocomplete="off"
          class="flex-1 min-w-[12rem] border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <select v-model="nuevo.tipo"
          class="border border-gray-200 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
          <option v-for="t in TIPOS" :key="t.key" :value="t.key">{{ t.singular }}</option>
        </select>
        <input v-model="nuevo.unidad" maxlength="20" placeholder="Unidad" list="unidades-inventario" autocomplete="off"
          class="w-28 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <button type="submit" :disabled="!nuevo.nombre.trim() || !nuevo.unidad.trim() || guardando"
          class="bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition disabled:opacity-40">
          Agregar
        </button>
      </div>
      <p class="text-xs text-gray-400 mt-2">{{ ayudaTipo }} Queda al final de su tipo; súbelo con ▲.</p>
      <datalist id="unidades-inventario">
        <option v-for="u in unidades" :key="u" :value="u" />
      </datalist>
    </form>

    <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>
    <p v-if="cargando" class="text-sm text-gray-400 mb-4">Cargando items…</p>

    <!-- Activos por tipo -->
    <div v-for="t in TIPOS" :key="t.key" class="bg-white rounded-2xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
      <div class="px-5 py-3 bg-gray-50 border-b border-gray-200">
        <h3 class="font-bold text-gray-700">{{ t.emoji }} {{ t.label }}</h3>
      </div>
      <div class="divide-y divide-gray-100">
        <div v-for="(it, i) in activosDe(t.key)" :key="it.id" class="px-5 py-2 flex items-center gap-2">
          <div class="flex flex-col shrink-0">
            <button @click="mover(it, activosDe(t.key)[i - 1])" :disabled="i === 0 || guardando" title="Subir"
              class="text-xs leading-none px-1 text-gray-500 hover:text-orange-600 disabled:opacity-20">▲</button>
            <button @click="mover(it, activosDe(t.key)[i + 1])" :disabled="i === activosDe(t.key).length - 1 || guardando" title="Bajar"
              class="text-xs leading-none px-1 text-gray-500 hover:text-orange-600 disabled:opacity-20">▼</button>
          </div>
          <span class="text-xs text-gray-400 w-6 text-right shrink-0">{{ i + 1 }}.</span>

          <template v-if="editando.id === it.id">
            <input v-model="editando.nombre" maxlength="100" @keydown.enter.prevent="guardarEdicion(it)" @keydown.esc="editando.id = null"
              class="flex-1 min-w-0 border border-gray-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <select v-model="editando.tipo" class="border border-gray-200 rounded-lg px-1 py-1 text-xs">
              <option v-for="tt in TIPOS" :key="tt.key" :value="tt.key">{{ tt.singular }}</option>
            </select>
            <input v-model="editando.unidad" maxlength="20" list="unidades-inventario" @keydown.enter.prevent="guardarEdicion(it)"
              class="w-20 border border-gray-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <button @click="guardarEdicion(it)" :disabled="guardando"
              class="text-xs bg-orange-500 hover:bg-orange-600 text-white px-2 py-1 rounded font-medium disabled:opacity-40">Guardar</button>
            <button @click="editando.id = null" class="text-xs text-gray-500 hover:text-gray-700 px-1">Cancelar</button>
          </template>
          <template v-else>
            <span class="flex-1 min-w-0 text-sm text-gray-800 font-medium truncate">{{ it.nombre }}</span>
            <span class="text-xs text-gray-400 shrink-0">{{ it.unidad }}</span>
            <button @click="editar(it)" :disabled="guardando"
              class="text-xs border border-gray-200 hover:border-orange-300 text-gray-600 px-2 py-1 rounded font-medium disabled:opacity-40">Editar</button>
            <button @click="cambiarActivo(it, false)" :disabled="guardando"
              class="text-xs bg-red-50 hover:bg-red-100 text-red-600 px-2 py-1 rounded font-medium disabled:opacity-40">Desactivar</button>
          </template>
        </div>
        <div v-if="activosDe(t.key).length === 0" class="px-5 py-4 text-sm text-gray-400 text-center">Sin items</div>
      </div>
    </div>

    <!-- Inactivos -->
    <div v-if="inactivos.length" class="bg-white rounded-2xl border border-gray-200 p-5 mb-4">
      <h3 class="font-bold text-gray-500 text-sm mb-2">Items inactivos (no se cuentan ni se pueden usar en recetas nuevas)</h3>
      <div v-for="it in inactivos" :key="it.id" class="flex items-center justify-between py-1.5 text-sm">
        <span class="text-gray-400">{{ it.nombre }} · {{ tipoSingular(it.tipo) }} · {{ it.unidad }}</span>
        <button @click="cambiarActivo(it, true)" :disabled="guardando"
          class="text-xs bg-green-50 hover:bg-green-100 text-green-700 px-2 py-1 rounded font-medium disabled:opacity-40">Reactivar</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '@/services/api'

// Mismo orden y nombres que el Inventario Diario.
const TIPOS = [
  { key: 'vendible', label: 'Vendibles', singular: 'Vendible', emoji: '🍗',
    ayuda: 'Vendible: se vende tal cual (pollo, costilla, bebidas).' },
  { key: 'insumo', label: 'Insumos', singular: 'Insumo', emoji: '🧂',
    ayuda: 'Insumo: se usa para preparar (arroz, mayonesa, porciones).' },
  { key: 'desechable', label: 'Desechables', singular: 'Desechable', emoji: '🥡',
    ayuda: 'Desechable: empaque (bolsas, platos, vasitos).' },
]
const URL = '/api/inventario/items'

const items = ref([])
const cargando = ref(false)
const guardando = ref(false)
const errorMsg = ref('')
const nuevo = reactive({ nombre: '', tipo: 'vendible', unidad: 'unidad' })
const editando = reactive({ id: null, nombre: '', tipo: '', unidad: '' })

const ayudaTipo = computed(() => TIPOS.find((t) => t.key === nuevo.tipo)?.ayuda || '')
const inactivos = computed(() => items.value.filter((i) => !i.activo))
const unidades = computed(() => [...new Set(items.value.map((i) => i.unidad))].sort())
function activosDe(tipo) {
  return items.value.filter((i) => i.activo && i.tipo === tipo)
}
function tipoSingular(tipo) {
  return TIPOS.find((t) => t.key === tipo)?.singular || tipo
}

function mensajeError(e, porDefecto) {
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x) => x.msg).join(' · ')
  return d || porDefecto
}

async function cargar() {
  cargando.value = true
  try {
    const { data } = await api.get(URL, { params: { incluir_inactivos: true } })
    items.value = data
  } catch (e) {
    errorMsg.value = mensajeError(e, 'No se pudieron cargar los items')
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)

// Toda escritura: ejecuta, muestra el error del backend si lo hay y recarga.
async function escribir(fn, porDefecto) {
  guardando.value = true
  errorMsg.value = ''
  try {
    await fn()
    return true
  } catch (e) {
    errorMsg.value = mensajeError(e, porDefecto)
    return false
  } finally {
    await cargar()
    guardando.value = false
  }
}

async function agregar() {
  const body = { nombre: nuevo.nombre.trim(), tipo: nuevo.tipo, unidad: nuevo.unidad.trim() }
  if (!body.nombre || !body.unidad) return
  const ok = await escribir(() => api.post(URL, body), 'No se pudo agregar el item')
  if (ok) nuevo.nombre = ''
}

function editar(it) {
  Object.assign(editando, { id: it.id, nombre: it.nombre, tipo: it.tipo, unidad: it.unidad })
}

async function guardarEdicion(it) {
  const body = { nombre: editando.nombre.trim(), tipo: editando.tipo, unidad: editando.unidad.trim() }
  if (!body.nombre || !body.unidad) return
  const ok = await escribir(() => api.put(`${URL}/${it.id}`, body), 'No se pudo guardar el item')
  if (ok) editando.id = null
}

function cambiarActivo(it, activo) {
  if (!activo && !confirm(`¿Desactivar "${it.nombre}"? Dejará de aparecer en el Inventario Diario.`)) return
  escribir(() => api.put(`${URL}/${it.id}`, { activo }), 'No se pudo cambiar el item')
}

// ▲ ▼: intercambia el lugar de dos items del mismo tipo en la lista completa
// (orden de conteo) y la envía entera.
function mover(it, otro) {
  if (!otro) return
  const ids = items.value.map((i) => i.id)
  const a = ids.indexOf(it.id)
  const b = ids.indexOf(otro.id)
  ;[ids[a], ids[b]] = [ids[b], ids[a]]
  escribir(() => api.put(`${URL}/orden`, { ids }), 'No se pudo cambiar el orden')
}
</script>
