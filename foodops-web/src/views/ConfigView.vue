<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Configuración del menú</h1>
      <RouterLink to="/pos" class="text-sm text-gray-500 hover:text-gray-700">← POS</RouterLink>
    </div>

    <!-- Sección por categoría -->
    <div v-for="cat in categorias" :key="cat.key" class="bg-white rounded-2xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
      <div class="flex items-center justify-between px-5 py-3 bg-gray-50 border-b border-gray-200">
        <h3 class="font-bold text-gray-700">{{ cat.emoji }} {{ cat.label }}</h3>
        <button @click="abrirNuevo(cat.key)"
          class="text-xs bg-orange-500 hover:bg-orange-600 text-white px-3 py-1.5 rounded-full font-semibold transition">
          + Agregar
        </button>
      </div>

      <!-- Lista de items existentes -->
      <div class="divide-y divide-gray-100">
        <div v-for="item in itemsPorCategoria(cat.key)" :key="item.id" class="px-5 py-3">
          <!-- Fila principal: emoji, nombre, precio, eliminar -->
          <div class="flex items-center gap-3">
            <button @click="cambiarEmoji(item)" class="text-2xl hover:scale-110 transition-transform" title="Cambiar emoji">
              {{ item.emoji }}
            </button>
            <input v-model="item.nombre"
              class="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 font-medium" />
            <div class="flex items-center gap-1 shrink-0">
              <span class="text-xs text-gray-400 font-medium">Q</span>
              <input v-model.number="item.precio" type="number" min="0"
                class="w-20 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 font-bold text-orange-600" />
            </div>
            <button @click="eliminarItem(item.id)"
              class="text-red-400 hover:text-red-600 text-lg font-bold leading-none px-1 transition" title="Eliminar">
              ✕
            </button>
          </div>
          <!-- Contenido del combo (editable) -->
          <div v-if="item.categoria === 'combos'" class="mt-2 ml-9">
            <label class="text-xs text-gray-400 font-medium block mb-1">Contenido del combo:</label>
            <input v-model="item.contenido" placeholder="Ej: 1 pollo entero, 3 guarniciones, 5 cebollines"
              class="w-full border border-gray-100 rounded-lg px-2 py-1.5 text-xs text-gray-600 focus:outline-none focus:ring-1 focus:ring-orange-300 bg-gray-50" />
          </div>
          <!-- Unidad (editable) -->
          <div class="mt-1 ml-9 flex items-center gap-2">
            <label class="text-xs text-gray-400">Unidad:</label>
            <input v-model="item.unidad" placeholder="pieza / lb / porción / combo"
              class="border border-gray-100 rounded-lg px-2 py-1 text-xs text-gray-500 focus:outline-none focus:ring-1 focus:ring-orange-200 bg-gray-50 w-32" />
          </div>
        </div>
      </div>

      <div v-if="itemsPorCategoria(cat.key).length === 0" class="px-5 py-4 text-sm text-gray-400 text-center">
        Sin productos en esta categoría
      </div>
    </div>

    <!-- Nueva categoría -->
    <div class="bg-white rounded-2xl border border-dashed border-gray-300 p-5 mb-6">
      <h3 class="font-bold text-gray-600 mb-3">➕ Nueva categoría</h3>
      <div class="flex gap-2">
        <input v-model="nuevaCatKey" placeholder="clave (ej: bebidas)" autocomplete="off"
          class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <input v-model="nuevaCatLabel" placeholder="nombre (ej: Bebidas)" autocomplete="off"
          class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <input v-model="nuevaCatEmoji" placeholder="🥤" autocomplete="off"
          class="w-14 border border-gray-200 rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <button @click="agregarCategoria"
          class="bg-gray-700 hover:bg-gray-800 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
          Crear
        </button>
      </div>
    </div>

    <!-- Acciones -->
    <p v-if="guardado" class="text-green-600 text-sm text-center font-semibold mb-3">✓ Menú guardado</p>
    <div class="flex gap-3">
      <button @click="guardar"
        class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition">
        💾 Guardar cambios
      </button>
      <button @click="resetear"
        class="border border-gray-300 text-gray-500 text-sm px-4 py-3 rounded-xl hover:bg-gray-50 transition">
        Restablecer
      </button>
    </div>

    <!-- Modal: nuevo producto -->
    <div v-if="nuevoModal.visible" class="fixed inset-0 bg-black bg-opacity-50 flex items-end sm:items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl w-full max-w-md p-6 shadow-2xl">
        <h3 class="font-bold text-gray-800 mb-4">Nuevo producto — {{ catLabel(nuevoModal.categoria) }}</h3>
        <div class="space-y-3">
          <div class="flex gap-2">
            <div class="flex flex-col gap-1">
              <label class="text-xs text-gray-500">Emoji</label>
              <input v-model="nuevoModal.emoji" maxlength="4" autocomplete="off"
                class="w-16 border border-gray-200 rounded-lg px-2 py-2 text-xl text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div class="flex-1 flex flex-col gap-1">
              <label class="text-xs text-gray-500">Nombre *</label>
              <input v-model="nuevoModal.nombre" placeholder="Nombre del producto" autocomplete="off"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>
          <div class="flex gap-2">
            <div class="flex flex-col gap-1 flex-1">
              <label class="text-xs text-gray-500">Precio (Q) *</label>
              <input v-model.number="nuevoModal.precio" type="number" min="0" placeholder="0" autocomplete="off"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div class="flex flex-col gap-1 flex-1">
              <label class="text-xs text-gray-500">Unidad</label>
              <input v-model="nuevoModal.unidad" placeholder="pieza / lb / porción" autocomplete="off"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>
          <div v-if="nuevoModal.categoria === 'combos'" class="flex flex-col gap-1">
            <label class="text-xs text-gray-500">Contenido del combo</label>
            <input v-model="nuevoModal.contenido" placeholder="Ej: 1 pollo entero, 3 guarniciones..." autocomplete="off"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>
        </div>
        <p v-if="nuevoModal.error" class="text-red-500 text-xs mt-2">{{ nuevoModal.error }}</p>
        <div class="flex gap-3 mt-5">
          <button @click="nuevoModal.visible = false"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50 transition">
            Cancelar
          </button>
          <button @click="confirmarNuevo"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl transition">
            Agregar
          </button>
        </div>
      </div>
    </div>

    <!-- Modal: cambiar emoji -->
    <div v-if="emojiModal.visible" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl w-80 p-5 shadow-2xl">
        <h3 class="font-bold text-gray-800 mb-3">Cambiar emoji</h3>
        <div class="grid grid-cols-6 gap-2 mb-4">
          <button v-for="e in emojiOpciones" :key="e" @click="seleccionarEmoji(e)"
            class="text-2xl p-2 rounded-xl hover:bg-orange-50 hover:scale-110 transition-transform">{{ e }}</button>
        </div>
        <input v-model="emojiModal.custom" maxlength="4" placeholder="O escribe un emoji..."
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-center text-xl mb-3 focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <div class="flex gap-2">
          <button @click="emojiModal.visible = false"
            class="flex-1 border border-gray-200 text-gray-500 py-2 rounded-xl text-sm hover:bg-gray-50">Cancelar</button>
          <button @click="aplicarEmojiCustom" :disabled="!emojiModal.custom"
            class="flex-1 bg-orange-500 text-white py-2 rounded-xl text-sm font-bold disabled:opacity-40">Aplicar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { getMenu, saveMenu, MENU_ITEMS, CATEGORIAS } from '@/data/menu.js'

const guardado = ref(false)
const menu = reactive(JSON.parse(JSON.stringify(getMenu())))

// Categorías dinámicas (pueden crecer)
const categorias = reactive(JSON.parse(JSON.stringify(CATEGORIAS)).map(c => ({
  ...c,
  emoji: { pollos: '🍗', costillas: '🥓', combos: '🥘', guarniciones: '🥔', extras: '➕' }[c.key] || '📦',
})))

// Nueva categoría
const nuevaCatKey = ref('')
const nuevaCatLabel = ref('')
const nuevaCatEmoji = ref('')

function agregarCategoria() {
  const key = nuevaCatKey.value.trim().toLowerCase().replace(/\s+/g, '_')
  const label = nuevaCatLabel.value.trim()
  if (!key || !label) return
  if (categorias.find(c => c.key === key)) return
  categorias.push({ key, label, emoji: nuevaCatEmoji.value || '📦' })
  nuevaCatKey.value = ''
  nuevaCatLabel.value = ''
  nuevaCatEmoji.value = ''
}

function catLabel(key) {
  return categorias.find(c => c.key === key)?.label || key
}

function itemsPorCategoria(cat) {
  return menu.filter(i => i.categoria === cat)
}

function eliminarItem(id) {
  if (!confirm('¿Eliminar este producto del menú?')) return
  const idx = menu.findIndex(i => i.id === id)
  if (idx !== -1) menu.splice(idx, 1)
}

// ─── Modal nuevo producto ───
const nuevoModal = reactive({
  visible: false,
  categoria: '',
  emoji: '',
  nombre: '',
  precio: '',
  unidad: 'porción',
  contenido: '',
  error: '',
})

function abrirNuevo(cat) {
  Object.assign(nuevoModal, {
    visible: true, categoria: cat, emoji: '', nombre: '', precio: '',
    unidad: 'porción', contenido: '', error: '',
  })
}

function confirmarNuevo() {
  nuevoModal.error = ''
  if (!nuevoModal.nombre.trim()) { nuevoModal.error = 'El nombre es requerido'; return }
  if (!nuevoModal.precio || nuevoModal.precio < 0) { nuevoModal.error = 'Ingresa un precio válido'; return }
  const maxId = menu.reduce((m, i) => Math.max(m, i.id || 0), 0)
  const nuevo = {
    id: maxId + 1,
    nombre: nuevoModal.nombre.trim(),
    precio: Number(nuevoModal.precio),
    categoria: nuevoModal.categoria,
    unidad: nuevoModal.unidad || 'porción',
    emoji: nuevoModal.emoji || '🍽️',
  }
  if (nuevoModal.categoria === 'combos' && nuevoModal.contenido) {
    nuevo.contenido = nuevoModal.contenido.trim()
  }
  menu.push(nuevo)
  nuevoModal.visible = false
}

// ─── Modal emoji ───
const emojiOpciones = [
  '🍗','🥓','🥘','🔥','👑','🥔','🍚','🥗','🧀','🍝',
  '🌶️','🫑','🧅','🧄','🍋','🥤','🧃','🍺','🥛','☕',
  '🍕','🌮','🌯','🥙','🥚','🍳','🥞','🧇','🫔','🥣',
  '🍖','🫕','🥩','🥦','🫛','🌽','🫚','🫙','🥫','🍱',
  '➕','🎁','⭐','💎','🏆','🎯','🔑','🎪','🎠','🎡',
]

const emojiModal = reactive({ visible: false, item: null, custom: '' })

function cambiarEmoji(item) {
  emojiModal.item = item
  emojiModal.custom = ''
  emojiModal.visible = true
}

function seleccionarEmoji(e) {
  if (emojiModal.item) emojiModal.item.emoji = e
  emojiModal.visible = false
}

function aplicarEmojiCustom() {
  if (emojiModal.item && emojiModal.custom) emojiModal.item.emoji = emojiModal.custom
  emojiModal.visible = false
}

// ─── Guardar / resetear ───
function guardar() {
  saveMenu(menu)
  guardado.value = true
  setTimeout(() => guardado.value = false, 2500)
}

function resetear() {
  if (!confirm('¿Restaurar el menú original? Se perderán todos los cambios.')) return
  menu.splice(0, menu.length, ...JSON.parse(JSON.stringify(MENU_ITEMS)))
  localStorage.removeItem('foodops_menu')
}
</script>
