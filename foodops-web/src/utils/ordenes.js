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
