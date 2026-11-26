// Fetch de órdenes con caché local para modo offline. Antes vivía duplicado
// (idéntico) en DashboardView.vue y OrdenesView.vue.
//
// La caché se guarda por tienda activa, no bajo una sola clave global: antes,
// alternar el selector de tienda a una sucursal sin órdenes y luego volver a
// "Todas las tiendas" dejaba la caché compartida sobrescrita con []; si esa
// segunda carga fallaba por cualquier motivo, se servía ese [] obsoleto en
// vez de las órdenes reales. Con clave por filtro, un fallo de red solo
// puede servir caché del mismo filtro que se está pidiendo.
import api from '@/services/api'

const CACHE_PREFIX = 'foodops_ordenes'

function cacheKey() {
  const puntoActivo = localStorage.getItem('punto_activo')
  return `${CACHE_PREFIX}_${puntoActivo || 'todas'}`
}

// Para actualizar la caché del filtro actual tras una acción local (ej. una
// orden recién creada), sin tener que volver a pedirle todo al backend.
export function guardarOrdenesEnCache(ordenes) {
  localStorage.setItem(cacheKey(), JSON.stringify(ordenes))
}

// Devuelve { ordenes, deCache }. deCache=true cuando la petición real falló
// (sin conexión u otro error) y se sirvió la última copia guardada de ESTE
// mismo filtro - nunca de otro.
export async function fetchOrdenesConCache() {
  const key = cacheKey()
  try {
    const { data } = await api.get('/api/ordenes/')
    localStorage.setItem(key, JSON.stringify(data))
    return { ordenes: data, deCache: false }
  } catch (e) {
    console.error('No se pudieron cargar las órdenes desde el servidor, usando caché local:', e)
    const cached = localStorage.getItem(key)
    return { ordenes: cached ? JSON.parse(cached) : [], deCache: true }
  }
}

// Mensaje para un error de PUT /api/ordenes/{id}/status. El 403 (rol sin
// permiso) y el 409 (orden cancelada) tienen un texto propio en vez del
// genérico.
export function mensajeErrorEstado(e) {
  const status = e?.response?.status
  const detalle = e?.response?.data?.detail
  if (status === 403) {
    return 'No tienes permiso para cambiar el estado de esta orden. Pídeselo a cocina o al responsable de la tienda.'
  }
  if (status === 409 && detalle) return detalle
  return detalle || 'No se pudo actualizar el estado de la orden.'
}

// Etiquetas del estado de cocina de una orden. Única fuente para Órdenes y
// Cocina (antes vivían solo en las pestañas de OrdersListView).
export const ETIQUETAS_ESTADO = {
  pendiente: 'Pendiente',
  preparando: 'Preparando',
  listo: 'Listo',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
}

export function etiquetaEstado(estado) {
  return ETIQUETAS_ESTADO[estado] || estado
}

// Mensaje para un error de PUT /api/ordenes/{id}/responsable-cocina: el
// detalle del backend ya dice qué pasó (otra tienda, inactivo, orden lista,
// solo gerencia reasigna).
export function mensajeErrorResponsable(e) {
  return e?.response?.data?.detail || 'No se pudo asignar el responsable de cocina.'
}

// Texto del botón de listo/entregado cuando falta el responsable de cocina.
export const TEXTO_ASIGNA_RESPONSABLE = 'Asigna responsable'
