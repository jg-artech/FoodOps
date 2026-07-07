<template>
  <div class="max-w-2xl mx-auto px-4 py-6">

    <!-- Barra de progreso -->
    <div class="flex items-center justify-between mb-5">
      <button @click="goBack" class="text-gray-500 hover:text-gray-700 text-sm">← Volver</button>
      <div class="flex gap-1.5">
        <span v-for="i in 4" :key="i" class="h-2 rounded-full transition-all"
          :class="[step >= i ? 'bg-orange-500' : 'bg-gray-200', step === i ? 'w-8' : 'w-4']" />
      </div>
      <span class="text-xs text-gray-400">{{ step }}/4</span>
    </div>

    <!-- ───── PASO 1: Tipo de cliente ───── -->
    <div v-if="step === 1">
      <h2 class="text-xl font-bold text-gray-800 mb-6">¿Cómo deseas ordenar?</h2>
      <div class="grid grid-cols-2 gap-4 mb-6">
        <button @click="form.tipo = 'llevar'"
          class="p-8 rounded-2xl border-2 text-center transition-all"
          :class="form.tipo === 'llevar' ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-600 hover:border-orange-300'">
          <div class="text-4xl mb-2">🥡</div>
          <div class="font-bold text-lg">Para llevar</div>
        </button>
        <button @click="form.tipo = 'domicilio'"
          class="p-8 rounded-2xl border-2 text-center transition-all"
          :class="form.tipo === 'domicilio' ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-600 hover:border-orange-300'">
          <div class="text-4xl mb-2">🏠</div>
          <div class="font-bold text-lg">Domicilio</div>
        </button>
      </div>

      <transition name="slide">
        <div v-if="form.tipo === 'domicilio'" class="space-y-3 mb-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Nombre cliente *</label>
            <input v-model="form.cliente_nombre" type="text" placeholder="Juan Pérez" autocomplete="off"
              class="w-full border border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Teléfono *</label>
            <input v-model="form.cliente_telefono" type="tel" placeholder="5000-0000" autocomplete="off"
              class="w-full border border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Dirección *</label>
            <input v-model="form.cliente_direccion" type="text" placeholder="Zona 3, San Lucas" autocomplete="off"
              class="w-full border border-gray-300 rounded-xl px-3 py-3 focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>
        </div>
      </transition>

      <button @click="step = 2" :disabled="!canStep1"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-4 rounded-xl text-lg transition disabled:opacity-40">
        Siguiente →
      </button>
    </div>

    <!-- ───── PASO 2: Seleccionar productos ───── -->
    <div v-if="step === 2">
      <h2 class="text-xl font-bold text-gray-800 mb-1">Seleccionar productos</h2>
      <p class="text-sm text-gray-400 mb-5">Toca [+] para agregar</p>

      <div v-for="cat in categorias" :key="cat.key" class="mb-6">
        <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">{{ cat.label }}</h3>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div v-for="item in itemsPorCategoria(cat.key)" :key="item.id"
            class="bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
            <div class="text-2xl mb-1">{{ item.emoji }}</div>
            <p class="font-semibold text-gray-800 text-sm leading-tight">{{ item.nombre }}</p>
            <p v-if="item.contenido" class="text-xs text-gray-400 mt-0.5 leading-tight">{{ item.contenido }}</p>
            <p class="text-orange-500 font-bold mt-1 mb-2">Q{{ item.precio }}</p>
            <div class="flex items-center justify-between">
              <button @click="quitarItem(item)"
                class="w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 font-bold flex items-center justify-center text-lg">−</button>
              <span class="font-bold text-base w-6 text-center">{{ getTotalQty(item.id) }}</span>
              <button @click="agregarItem(item)"
                class="w-8 h-8 rounded-full bg-orange-500 hover:bg-orange-600 text-white font-bold flex items-center justify-center text-lg">+</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Total flotante -->
      <div class="sticky bottom-4 bg-white border border-gray-200 rounded-2xl shadow-xl p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-400">{{ totalItems }} producto(s)</p>
          <p class="text-2xl font-bold text-orange-500">Q{{ totalPrecio.toFixed(2) }}</p>
        </div>
        <button @click="step = 3" :disabled="cart.length === 0"
          class="bg-orange-500 hover:bg-orange-600 text-white font-bold px-6 py-3 rounded-xl transition disabled:opacity-40">
          Revisar →
        </button>
      </div>
    </div>

    <!-- ───── PASO 3: Resumen + requerimientos especiales ───── -->
    <div v-if="step === 3">
      <h2 class="text-xl font-bold text-gray-800 mb-4">Resumen de orden</h2>

      <div class="bg-white border border-gray-200 rounded-2xl p-5 mb-4 shadow-sm">
        <p class="font-semibold text-gray-700 mb-1">
          {{ form.tipo === 'domicilio' ? `🏠 Domicilio — ${form.cliente_nombre}` : '🥡 Para llevar' }}
        </p>
        <div v-if="form.tipo === 'domicilio'" class="text-sm text-gray-400 mb-3 space-y-0.5">
          <p>📞 {{ form.cliente_telefono }}</p>
          <p>📍 {{ form.cliente_direccion }}</p>
        </div>
        <hr class="mb-3">

        <!-- Items del carrito agrupados -->
        <div class="space-y-1">
          <div v-for="entry in cart" :key="entry.cartKey" class="flex items-center justify-between text-sm">
            <div class="flex items-center gap-2">
              <button @click="quitarCartEntry(entry.cartKey)"
                class="w-5 h-5 rounded-full bg-red-100 hover:bg-red-200 text-red-600 text-xs font-bold flex items-center justify-center">−</button>
              <span class="text-gray-700">{{ entry.cantidad }}x {{ entry.nombre }}</span>
            </div>
            <span class="font-semibold text-gray-700">Q{{ (entry.cantidad * entry.precio).toFixed(2) }}</span>
          </div>
        </div>
        <hr class="my-3">
        <div class="flex justify-between font-bold text-lg">
          <span>TOTAL</span>
          <span class="text-orange-500">Q{{ totalPrecio.toFixed(2) }}</span>
        </div>
      </div>

      <!-- Preview de componentes a descontar de inventario -->
      <div v-if="componentesPreview.length" class="bg-blue-50 border border-blue-200 rounded-2xl p-4 mb-4">
        <p class="font-semibold text-blue-800 text-sm mb-2">📦 Al confirmar, se registrarán estos componentes:</p>
        <ul class="text-sm text-blue-700 space-y-0.5">
          <li v-for="c in componentesPreview" :key="c.item_id">
            {{ c.cantidad }} {{ c.unidad || '' }} {{ c.nombre }}
          </li>
        </ul>
      </div>

      <!-- Requerimientos especiales -->
      <div class="bg-amber-50 border border-amber-200 rounded-2xl p-4 mb-4">
        <label class="block font-semibold text-amber-800 mb-2">⚠️ Requerimientos especiales</label>
        <p class="text-xs text-amber-600 mb-2">Instrucciones para cocina (sin picante, extra cebollín, bien cocido...)</p>
        <textarea v-model="form.notas_especiales" rows="3"
          placeholder="Ej: Sin jalapeño en combo, extra cebollín, bien cocido"
          class="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white resize-none"></textarea>
      </div>

      <div class="flex gap-3">
        <button @click="step = 2" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
          ← Editar
        </button>
        <button @click="step = 4" class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition">
          Pagar →
        </button>
      </div>
    </div>

    <!-- ───── PASO 4: Método de pago ───── -->
    <div v-if="step === 4">
      <h2 class="text-xl font-bold text-gray-800 mb-2">¿Cómo paga?</h2>
      <p class="text-2xl font-black text-orange-500 mb-5">Total: Q{{ totalPrecio.toFixed(2) }}</p>

      <div class="space-y-3 mb-4">
        <button v-for="m in metodos" :key="m.value" @click="form.metodo_pago = m.value; form.dinero_recibido = ''"
          class="w-full p-5 border-2 rounded-2xl flex items-center gap-4 transition-all"
          :class="form.metodo_pago === m.value ? 'border-orange-500 bg-orange-50' : 'border-gray-200 hover:border-gray-300'">
          <span class="text-3xl">{{ m.emoji }}</span>
          <span class="font-bold text-xl">{{ m.label }}</span>
        </button>
      </div>

      <!-- Panel de efectivo -->
      <transition name="slide">
        <div v-if="form.metodo_pago === 'efectivo'" class="bg-green-50 border border-green-200 rounded-2xl p-5 mb-4">
          <label class="block text-sm font-bold text-green-800 mb-3">💵 Efectivo recibido</label>
          <div class="flex items-center gap-3 mb-4">
            <span class="text-lg font-bold text-gray-500">Q</span>
            <input v-model.number="form.dinero_recibido" type="number" min="0" step="1"
              placeholder="0.00" autofocus
              class="flex-1 text-3xl font-black text-center border-2 border-green-300 rounded-xl px-4 py-3 focus:outline-none focus:border-green-500 bg-white" />
          </div>

          <!-- Botones rápidos de billetes -->
          <div class="grid grid-cols-4 gap-2 mb-4">
            <button v-for="b in billetes" :key="b" @click="form.dinero_recibido = b"
              class="py-2 rounded-xl text-sm font-bold border-2 transition-all"
              :class="form.dinero_recibido === b ? 'border-green-500 bg-green-500 text-white' : 'border-gray-200 bg-white text-gray-700 hover:border-green-400'">
              Q{{ b }}
            </button>
          </div>

          <!-- Vuelto -->
          <div v-if="form.dinero_recibido > 0" class="rounded-xl p-4 text-center"
            :class="vuelto >= 0 ? 'bg-white border border-green-300' : 'bg-red-50 border border-red-300'">
            <p class="text-xs font-bold uppercase tracking-wide mb-1"
              :class="vuelto >= 0 ? 'text-green-700' : 'text-red-600'">
              {{ vuelto >= 0 ? 'Vuelto' : '⚠️ Falta' }}
            </p>
            <p class="text-4xl font-black"
              :class="vuelto >= 0 ? 'text-green-600' : 'text-red-500'">
              Q{{ Math.abs(vuelto).toFixed(2) }}
            </p>
          </div>
        </div>
      </transition>

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>

      <div class="flex gap-3">
        <button @click="step = 3" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
          ← Volver
        </button>
        <button @click="confirmarOrden" :disabled="!canConfirmar || loading"
          class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
          {{ loading ? 'Creando...' : `✓ CONFIRMAR — Q${totalPrecio.toFixed(2)}` }}
        </button>
      </div>
    </div>

    <!-- ───── ÉXITO ───── -->
    <div v-if="step === 5" class="text-center py-8">
      <div class="text-6xl mb-4">✅</div>
      <h2 class="text-2xl font-bold text-gray-800 mb-1">¡Orden creada!</h2>
      <p class="text-3xl font-bold text-orange-500 mb-3">{{ ordenCreada?.numero_orden }}</p>

      <!-- Resumen de efectivo si aplica -->
      <div v-if="ordenCreada?.metodo_pago === 'efectivo' && ordenCreada?.dinero_recibido"
        class="bg-green-50 border border-green-200 rounded-2xl p-4 mb-5 text-left">
        <div class="flex justify-between text-sm text-gray-600 mb-1">
          <span>Total orden:</span>
          <span class="font-bold">Q{{ Number(ordenCreada.total).toFixed(2) }}</span>
        </div>
        <div class="flex justify-between text-sm text-gray-600 mb-2">
          <span>Efectivo recibido:</span>
          <span class="font-bold">Q{{ Number(ordenCreada.dinero_recibido).toFixed(2) }}</span>
        </div>
        <div class="flex justify-between text-base font-black border-t border-green-200 pt-2">
          <span class="text-green-700">Vuelto:</span>
          <span class="text-green-600 text-xl">Q{{ Number(ordenCreada.vuelto || 0).toFixed(2) }}</span>
        </div>
      </div>

      <p v-else class="text-gray-500 mb-5">Total: <strong>Q{{ totalPrecio.toFixed(2) }}</strong></p>

      <div class="flex flex-col gap-3">
        <button @click="resetOrden" class="bg-orange-500 hover:bg-orange-600 text-white font-bold py-4 rounded-xl text-lg">
          🍗 Nueva Orden
        </button>
        <RouterLink to="/pos" class="border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl block hover:bg-gray-50">
          Volver al POS
        </RouterLink>
        <RouterLink to="/cocina" target="_blank" class="border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl block hover:bg-gray-50">
          🍳 Ver en cocina
        </RouterLink>
      </div>
    </div>

    <!-- Modal de selección de pieza -->
    <PiezaModal
      v-if="modalPieza.visible"
      :opciones="modalPieza.opciones"
      :precio="modalPieza.precio"
      @confirmar="onPiezaConfirmada"
      @cancelar="modalPieza.visible = false"
    />

    <!-- Modal de selección de componentes elegibles (guarnición / opcionales) -->
    <SelectorComponentesModal
      v-if="selectorModal.visible"
      :nombre="selectorModal.item?.nombre"
      :precio="selectorModal.item?.precio"
      :grupos="selectorModal.grupos"
      :fijos="selectorModal.fijos"
      @confirmar="onSeleccionConfirmada"
      @cancelar="selectorModal.visible = false"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/index'
import { getMenu, getCategorias } from '@/data/menu.js'
import PiezaModal from '@/components/PiezaModal.vue'
import SelectorComponentesModal from '@/components/SelectorComponentesModal.vue'
import api from '@/services/api'

const router = useRouter()
const auth = useAuthStore()

// Recetas (producto_menu_id -> componentes de items_inventario) para previsualizar
// qué se descontará de inventario. Si el producto no tiene receta cargada en el
// backend (p.ej. items de menú editados a mano vía Config), simplemente no aparece.
const recetas = ref({})
async function cargarRecetas() {
  try {
    const { data } = await api.get('/api/productos-menu')
    const map = {}
    for (const p of data) map[p.id] = p.componentes
    recetas.value = map
  } catch {
    recetas.value = {}
  }
}
onMounted(cargarRecetas)

const step = ref(1)
const loading = ref(false)
const errorMsg = ref('')
const ordenCreada = ref(null)

const menuItems = getMenu()
const categorias = getCategorias()

const form = reactive({
  tipo: '',
  cliente_nombre: '',
  cliente_telefono: '',
  cliente_direccion: '',
  metodo_pago: '',
  notas_especiales: '',
  dinero_recibido: '',
})

const billetes = [20, 50, 100, 200]

const vuelto = computed(() => {
  if (!form.dinero_recibido) return 0
  return Number(form.dinero_recibido) - totalPrecio.value
})

const canConfirmar = computed(() => {
  if (!form.metodo_pago) return false
  if (form.metodo_pago === 'efectivo' && form.dinero_recibido) {
    return Number(form.dinero_recibido) >= totalPrecio.value
  }
  return true
})

// Carrito: cada entrada es un item con cantidad
const cart = ref([])

const modalPieza = reactive({
  visible: false,
  item: null,
  opciones: [],
  precio: 0,
})

const selectorModal = reactive({
  visible: false,
  item: null,
  tipoPieza: null,
  grupos: [],
  fijos: [],
})

// Agrupa los componentes elegible=true de una receta usando el grupo_elegible
// formal (grupo_elegible + nombre_grupo, asignado desde ConfigView) cuando
// existe: cada número de grupo es un "elige 1" independiente (p.ej. Pieza de
// Pollo vs Guarnición). Para componentes elegibles legacy sin grupo asignado
// (datos previos a esta feature) se mantiene el heurístico anterior por
// items_inventario.tipo como fallback, así no dejan de mostrarse.
function agruparElegibles(componentes) {
  const elegibles = componentes.filter((c) => c.elegible)
  const conGrupo = elegibles.filter((c) => c.grupo_elegible != null)
  const sinGrupo = elegibles.filter((c) => c.grupo_elegible == null)

  const porGrupo = {}
  for (const c of conGrupo) {
    if (!porGrupo[c.grupo_elegible]) porGrupo[c.grupo_elegible] = { label: c.nombre_grupo || `Grupo ${c.grupo_elegible}`, items: [] }
    porGrupo[c.grupo_elegible].items.push(c)
  }

  const porTipo = {}
  for (const c of sinGrupo) {
    if (!porTipo[c.tipo]) porTipo[c.tipo] = []
    porTipo[c.tipo].push(c)
  }
  const gruposHeuristicos = Object.entries(porTipo).map(([tipo, items]) => ({
    label: tipo === 'insumo' ? 'Guarnición' : 'Opcionales',
    items,
  }))

  return [...Object.values(porGrupo), ...gruposHeuristicos]
}

const metodos = [
  { value: 'efectivo',       label: 'Efectivo',       emoji: '💵' },
  { value: 'tarjeta',        label: 'Tarjeta',         emoji: '💳' },
  { value: 'transferencia',  label: 'Transferencia',   emoji: '📱' },
]

const canStep1 = computed(() => {
  if (!form.tipo) return false
  if (form.tipo === 'domicilio') return form.cliente_nombre && form.cliente_telefono && form.cliente_direccion
  return true
})

const totalItems = computed(() => cart.value.reduce((acc, i) => acc + i.cantidad, 0))
const totalPrecio = computed(() => cart.value.reduce((acc, i) => acc + i.cantidad * i.precio, 0))

// Orden de despliegue: el pollo siempre primero (por nombre del item o de su
// grupo, p.ej. "Pollo Entero" o cualquier pieza del grupo "Pieza de Pollo"),
// luego el resto de la proteína, luego guarnición, luego el resto de
// ingredientes (condimentos/fijos).
function esPollo(c) {
  return `${c.nombre} ${c.nombre_grupo || ''}`.toLowerCase().includes('pollo')
}
function ordenComponente(c) {
  if (esPollo(c)) return 0
  if (c.tipo === 'vendible') return 1
  if (c.nombre_grupo && c.nombre_grupo !== 'Guarnición') return 2
  if (c.nombre_grupo === 'Guarnición') return 3
  return 4
}

const componentesPreview = computed(() => {
  const acumulado = {}
  for (const entry of cart.value) {
    const receta = recetas.value[entry.id] || []
    const fijos = receta.filter((c) => !c.elegible)
    const elegidos = entry.componentesSeleccionados || []
    for (const c of [...fijos, ...elegidos]) {
      if (!acumulado[c.item_id]) {
        acumulado[c.item_id] = {
          item_id: c.item_id, nombre: c.nombre, unidad: c.unidad, cantidad: 0,
          tipo: c.tipo, nombre_grupo: c.nombre_grupo,
        }
      }
      acumulado[c.item_id].cantidad += c.cantidad * entry.cantidad
    }
  }
  return Object.values(acumulado).sort((a, b) => ordenComponente(a) - ordenComponente(b))
})

function itemsPorCategoria(cat) {
  return menuItems.filter(i => i.categoria === cat)
}

function getTotalQty(id) {
  return cart.value.filter(i => i.id === id).reduce((acc, i) => acc + i.cantidad, 0)
}

// PiezaModal (requiereSeleccion/opciones en menu.js) es el mecanismo legacy
// de "elegir pieza": es solo una etiqueta de texto, no está ligado a
// items_inventario ni afecta transaccion_componentes. Si la receta del
// producto ya tiene un grupo_elegible formal (p.ej. "Pieza de Pollo"), ese
// grupo cubre la misma decisión pero correctamente ligado a stock, así que
// se ignora requiereSeleccion para no preguntar dos veces por lo mismo.
// Esto también autocorrige menús viejos guardados en localStorage que aún
// traigan requiereSeleccion=true de antes de que existiera el grupo formal.
function tieneGrupoElegibleFormal(itemId) {
  const receta = recetas.value[itemId] || []
  return receta.some((c) => c.elegible && c.grupo_elegible != null)
}

function agregarItem(item) {
  if (item.requiereSeleccion && !tieneGrupoElegibleFormal(item.id)) {
    modalPieza.item = item
    modalPieza.opciones = item.opciones
    modalPieza.precio = item.precio
    modalPieza.visible = true
    return
  }
  procesarSeleccionOAgregar(item, null)
}

function onPiezaConfirmada(tipo) {
  modalPieza.visible = false
  procesarSeleccionOAgregar(modalPieza.item, tipo)
}

// Si el producto tiene componentes elegible=true, abre el selector antes de
// agregarlo al carrito; si no, lo agrega directo (comportamiento previo).
function procesarSeleccionOAgregar(item, tipoPieza) {
  const receta = recetas.value[item.id] || []
  const grupos = agruparElegibles(receta)
  if (grupos.length) {
    selectorModal.item = item
    selectorModal.tipoPieza = tipoPieza
    selectorModal.grupos = grupos
    selectorModal.fijos = receta.filter((c) => !c.elegible)
    selectorModal.visible = true
    return
  }
  agregarAlCarrito(item, tipoPieza, [])
}

function onSeleccionConfirmada(seleccionados) {
  selectorModal.visible = false
  agregarAlCarrito(selectorModal.item, selectorModal.tipoPieza, seleccionados)
}

function agregarAlCarrito(item, tipoPieza, componentesSeleccionados) {
  const sufijoPieza = tipoPieza ? `-${tipoPieza}` : ''
  const sufijoElegidos = componentesSeleccionados.length
    ? '-' + componentesSeleccionados.map((c) => c.item_id).sort((a, b) => a - b).join('.')
    : ''
  const cartKey = `item-${item.id}${sufijoPieza}${sufijoElegidos}`
  const extra = [tipoPieza, ...componentesSeleccionados.map((c) => c.nombre)].filter(Boolean).join(', ')
  const nombre = extra ? `${item.nombre} (${extra})` : item.nombre

  const existing = cart.value.find((i) => i.cartKey === cartKey)
  if (existing) {
    existing.cantidad++
  } else {
    cart.value.push({
      cartKey, id: item.id, nombre, precio: item.precio, cantidad: 1,
      tipoPieza: tipoPieza || null,
      componentesSeleccionados,
    })
  }
}

function quitarItem(item) {
  // Quita el último agregado de ese producto
  const entries = cart.value.filter(i => i.id === item.id)
  if (!entries.length) return
  const last = entries[entries.length - 1]
  if (last.cantidad > 1) last.cantidad--
  else cart.value = cart.value.filter(i => i.cartKey !== last.cartKey)
}

function quitarCartEntry(cartKey) {
  const entry = cart.value.find(i => i.cartKey === cartKey)
  if (!entry) return
  if (entry.cantidad > 1) entry.cantidad--
  else cart.value = cart.value.filter(i => i.cartKey !== cartKey)
}

function goBack() {
  if (step.value > 1) step.value--
  else router.push('/pos')
}

function getCostosConfig() {
  try {
    return {
      simples: JSON.parse(localStorage.getItem('foodops_costos') || '{}'),
      combos:  JSON.parse(localStorage.getItem('foodops_combo_costos') || '{}'),
    }
  } catch { return { simples: {}, combos: {} } }
}

function getCostoItem(cartItem, config) {
  // Si tiene desglose de combo, usar ese total
  const combo = config.combos[cartItem.id]
  if (combo?.total) return combo.total
  // Si no, usar costo simple por unidad
  return config.simples[cartItem.id] || 0
}

async function confirmarOrden() {
  errorMsg.value = ''
  loading.value = true
  try {
    const dineroRecibido = form.metodo_pago === 'efectivo' && form.dinero_recibido
      ? Number(form.dinero_recibido) : null
    const vueltoCalc = dineroRecibido !== null ? dineroRecibido - totalPrecio.value : null

    const payload = {
      cliente_nombre:    form.tipo === 'domicilio' ? form.cliente_nombre : null,
      cliente_telefono:  form.tipo === 'domicilio' ? form.cliente_telefono : null,
      cliente_direccion: form.tipo === 'domicilio' ? form.cliente_direccion : null,
      metodo_pago:       form.metodo_pago,
      es_domicilio:      form.tipo === 'domicilio',
      notas_especiales:  form.notas_especiales || null,
      dinero_recibido:   dineroRecibido,
      vuelto:            vueltoCalc,
      items: cart.value.map(i => ({
        producto:        i.nombre,
        cantidad:        i.cantidad,
        precio_unitario: i.precio,
        especiales:      null,
      })),
    }
    const { data } = await api.post('/api/ordenes/', payload)
    ordenCreada.value = data

    // Registrar transacción financiera con costo correcto por tipo
    const config = getCostosConfig()
    const itemsTransaccion = cart.value.map(i => {
      const costoU = getCostoItem(i, config)
      return {
        nombre:            i.nombre,
        cantidad:          i.cantidad,
        unidad:            'pieza',
        precio_unitario:   i.precio,
        costo_unitario:    costoU,
        subtotal:          i.cantidad * i.precio,
        tipo_pieza:        i.tipoPieza || null,
        producto_menu_id:  i.id,
        componentes_elegidos: i.componentesSeleccionados?.length
          ? i.componentesSeleccionados.map((c) => c.item_id)
          : null,
      }
    })
    const costoTotal  = itemsTransaccion.reduce((s, i) => s + i.costo_unitario * i.cantidad, 0)
    const margenBruto = totalPrecio.value - costoTotal
    const margenPct   = totalPrecio.value > 0 ? Math.round((margenBruto / totalPrecio.value) * 100) : 0

    api.post('/api/ordenes/transacciones/', {
      punto_id:                  auth.puntoId || 2,
      orden_id:                  data.id,
      tipo_venta:                'individual',
      cliente_nombre:            form.tipo === 'domicilio' ? form.cliente_nombre : null,
      cliente_telefono:          form.tipo === 'domicilio' ? form.cliente_telefono : null,
      cliente_direccion:         form.tipo === 'domicilio' ? form.cliente_direccion : null,
      tipo_cliente:              form.tipo === 'domicilio' ? 'domicilio' : 'para_llevar',
      precio_venta:              totalPrecio.value,
      costo_total:               costoTotal,
      margen_bruto:              margenBruto,
      margen_pct:                margenPct,
      metodo_pago:               form.metodo_pago,
      items:                     itemsTransaccion,
      requerimientos_especiales: form.notas_especiales || null,
    }).catch(() => {})

    step.value = 5
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al crear la orden'
  } finally {
    loading.value = false
  }
}

function resetOrden() {
  step.value = 1
  cart.value = []
  Object.assign(form, { tipo: '', cliente_nombre: '', cliente_telefono: '', cliente_direccion: '', metodo_pago: '', notas_especiales: '', dinero_recibido: '' })
  ordenCreada.value = null
  errorMsg.value = ''
}
</script>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
