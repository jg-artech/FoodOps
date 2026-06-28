export const MENU_ITEMS = [
  // POLLOS
  { id: 1,  nombre: 'Pollo Entero',         precio: 75,  categoria: 'pollos',      unidad: 'pieza',   emoji: '🍗' },
  { id: 2,  nombre: '½ Pollo',              precio: 45,  categoria: 'pollos',      unidad: 'pieza',   emoji: '🍗' },
  {
    id: 3,
    nombre: '¼ Pollo',
    precio: 25,
    categoria: 'pollos',
    unidad: 'pieza',
    emoji: '🍗',
    requiereSeleccion: true,
    opciones: ['Pechuga', 'Cuadril', 'Pierna', 'Ala'],
  },

  // COSTILLAS
  { id: 4, nombre: '1 Lb Costilla',         precio: 50,  categoria: 'costillas',   unidad: 'lb',      emoji: '🥓' },
  { id: 5, nombre: '½ Lb Costilla',         precio: 25,  categoria: 'costillas',   unidad: 'lb',      emoji: '🥓' },

  // COMBOS
  {
    id: 6, nombre: 'Combo Familiar',         precio: 90,  categoria: 'combos',      unidad: 'combo',   emoji: '🥘',
    contenido: '1 pollo entero, 3 guarniciones, 5 cebollines, 1 jalapeño',
  },
  {
    id: 7, nombre: 'Super Combo',            precio: 130, categoria: 'combos',      unidad: 'combo',   emoji: '👑',
    contenido: '1 Pollo Entero, 1 Lb Costilla, 3 guarniciones, 8 cebollines, 2 jalapeños, 1.75L Pepsi',
  },
  {
    id: 8, nombre: 'Combo Costilla Familiar',precio: 140, categoria: 'combos',      unidad: 'combo',   emoji: '🔥',
    contenido: '3 Lb costillas, 3 guarniciones, 10 cebollín, 4 jalapeños, 1 chirmol, 1.75L Pepsi',
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

export function getMenu() {
  try {
    const saved = localStorage.getItem('foodops_menu')
    if (saved) return JSON.parse(saved)
  } catch {}
  return MENU_ITEMS
}

export function saveMenu(items) {
  localStorage.setItem('foodops_menu', JSON.stringify(items))
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
