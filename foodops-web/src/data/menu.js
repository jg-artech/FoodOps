import { reactive } from 'vue'
import api from '@/services/api'

export const MENU_ITEMS = [
  // POLLOS
  { id: 1,  nombre: 'Pollo Entero',         precio: 75,  categoria: 'pollos',      unidad: 'pieza',   emoji: '🍗' },
  { id: 2,  nombre: '½ Pollo',              precio: 45,  categoria: 'pollos',      unidad: 'pieza',   emoji: '🍗' },
  {
    // La elección de pieza (Pechuga+Ala / Cuadril+Pierna) ya no pasa por
    // PiezaModal/requiereSeleccion: vive como grupo_elegible formal en la
    // receta (producto_componentes) y se resuelve junto con Guarnición en
    // SelectorComponentesModal - ver agruparElegibles en NewOrderView.vue.
    id: 3,
    nombre: '¼ Pollo',
    precio: 25,
    categoria: 'pollos',
    unidad: 'pieza',
    emoji: '🍗',
  },

  // COSTILLAS
  { id: 4, nombre: '1 Lb Costilla',         precio: 50,  categoria: 'costillas',   unidad: 'lb',      emoji: '🥓' },
  { id: 5, nombre: '½ Lb Costilla',         precio: 25,  categoria: 'costillas',   unidad: 'lb',      emoji: '🥓' },

  // COMBOS
  {
    id: 6, nombre: 'Combo Familiar',         precio: 90,  categoria: 'combos',      unidad: 'combo',   emoji: '🥘',
  },
  {
    id: 7, nombre: 'Super Combo',            precio: 130, categoria: 'combos',      unidad: 'combo',   emoji: '👑',
  },
  {
    id: 8, nombre: 'Combo Costilla Familiar',precio: 140, categoria: 'combos',      unidad: 'combo',   emoji: '🔥',
  },

  // GUARNICIONES
  { id: 9,  nombre: 'Papa al vapor',        precio: 5,   categoria: 'guarniciones', unidad: 'porción', emoji: '🥔' },
  { id: 10, nombre: 'Arroz con verdura',     precio: 5,   categoria: 'guarniciones', unidad: 'porción', emoji: '🍚' },
  { id: 11, nombre: 'Ensalada Rusa',         precio: 5,   categoria: 'guarniciones', unidad: 'porción', emoji: '🥗' },
  { id: 12, nombre: 'Papas con queso',       precio: 10,  categoria: 'guarniciones', unidad: 'porción', emoji: '🧀' },
  { id: 13, nombre: 'Coditos',               precio: 5,   categoria: 'guarniciones', unidad: 'porción', emoji: '🍝' },

  // EXTRAS
  { id: 14, nombre: 'Porción Extra',         precio: 5,   categoria: 'extras',      unidad: 'porción', emoji: '➕' },
]

export const CATEGORIAS = [
  { key: 'pollos',       label: 'Pollos' },
  { key: 'costillas',    label: 'Costillas' },
  { key: 'combos',       label: 'Combos' },
  { key: 'guarniciones', label: 'Guarniciones' },
  { key: 'extras',       label: 'Extras' },
]

// ─── Menú desde la API ───
// La fuente de verdad del catálogo (nombre, precio, categoría, unidad y
// contenido) es GET /api/productos-menu. MENU_ITEMS ya no se usa como menú:
// solo aporta el emoji por nombre mientras el emoji no viva en la base.
// Si la API falla, se conserva lo último que se cargó en memoria (nunca los
// valores escritos a mano). El arreglo es reactivo y siempre el mismo, así
// que las vistas que lo leen se actualizan cuando llega la respuesta.
const menuItems = reactive([])
export const estadoMenu = reactive({ cargado: false, cargando: false, error: '' })
let cargaEnCurso = null

const EMOJIS_KEY = 'foodops_emojis'

function leerEmojis() {
  try { return JSON.parse(localStorage.getItem(EMOJIS_KEY) || '{}') } catch { return {} }
}

// Emoji elegido en Configuración (solo en este navegador), o el de MENU_ITEMS
// con el mismo nombre, o el de la categoría.
export function emojiDeProducto(producto, guardados = leerEmojis()) {
  return guardados[producto.id]
    || MENU_ITEMS.find((m) => m.nombre === producto.nombre)?.emoji
    || EMOJI_DEFAULT[producto.categoria]
    || '🍽️'
}

export function guardarEmoji(productoId, emoji) {
  const guardados = leerEmojis()
  guardados[productoId] = emoji
  localStorage.setItem(EMOJIS_KEY, JSON.stringify(guardados))
  const item = menuItems.find((i) => i.id === productoId)
  if (item) item.emoji = emoji
}

export function cargarMenu({ forzar = false } = {}) {
  if (cargaEnCurso) return cargaEnCurso
  if (estadoMenu.cargado && !forzar) return Promise.resolve(menuItems)
  estadoMenu.cargando = true
  cargaEnCurso = api.get('/api/productos-menu')
    .then(({ data }) => {
      const guardados = leerEmojis()
      menuItems.splice(0, menuItems.length, ...data.map((p) => ({ ...p, emoji: emojiDeProducto(p, guardados) })))
      estadoMenu.cargado = true
      estadoMenu.error = ''
      return menuItems
    })
    .catch(() => {
      estadoMenu.error = 'No se pudo cargar el menú'
      return menuItems
    })
    .finally(() => {
      estadoMenu.cargando = false
      cargaEnCurso = null
    })
  return cargaEnCurso
}

// Devuelve el arreglo reactivo del menú y lo carga la primera vez.
export function getMenu() {
  if (!estadoMenu.cargado) cargarMenu()
  return menuItems
}

// Producto del menú para un item de orden: por producto_menu_id si el item
// lo trae; si no, por nombre (exacto, o el nombre más largo con el que empieza,
// p. ej. "¼ Pollo (Pechuga+Ala)").
export function productoDeItem(item) {
  if (item?.producto_menu_id != null) {
    const porId = menuItems.find((m) => m.id === item.producto_menu_id)
    if (porId) return porId
  }
  const nombre = item?.producto || ''
  if (!nombre) return null
  const exacto = menuItems.find((m) => m.nombre === nombre)
  if (exacto) return exacto
  let mejor = null
  for (const m of menuItems) {
    if (nombre.startsWith(m.nombre) && (!mejor || m.nombre.length > mejor.nombre.length)) mejor = m
  }
  return mejor
}

export function contenidoDeItem(item) {
  return productoDeItem(item)?.contenido || null
}

const EMOJI_DEFAULT = {
  pollos: '🍗', costillas: '🥓', combos: '🥘', guarniciones: '🥔', extras: '➕',
}

export function getCategorias() {
  try {
    const saved = localStorage.getItem('foodops_categorias')
    if (saved) return JSON.parse(saved)
  } catch {}
  return CATEGORIAS.map(c => ({ ...c, emoji: EMOJI_DEFAULT[c.key] || '📦' }))
}

export function saveCategorias(cats) {
  localStorage.setItem('foodops_categorias', JSON.stringify(cats))
}
