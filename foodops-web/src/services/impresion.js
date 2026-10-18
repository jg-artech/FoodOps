// Impresión por agente de tienda (docs/DISENO_IMPRESION.md §7).
// Rutas, bodies y códigos: src/foodops/api/router_impresion.py.
//
// Nunca se envía punto_id en el body de ticket ni de abrir-cajon: el backend
// lo deriva de la orden o del usuario. En los GET, el interceptor de api.js
// agrega la tienda del selector de gerencia como siempre.
import api from '@/services/api'

// Códigos de los 409 de POST /ticket (detail.codigo). Se decide por código,
// nunca por el texto del mensaje.
export const COD_IMPRIMIR_INACTIVA = 'IMPRIMIR_INACTIVA'
export const COD_PENDIENTE_RECIBIR = 'PENDIENTE_RECIBIR'

// error = "caducado" en un ABRIR_CAJON que venció (120 s) antes de abrirse.
export const ERROR_CADUCADO = 'caducado'

export async function imprimirTicket(ordenId) {
  const { data } = await api.post('/api/impresion/ticket', { orden_id: ordenId })
  return data
}

export async function abrirCajon(motivo) {
  const { data } = await api.post('/api/impresion/abrir-cajon', { motivo })
  return data
}

export async function listarTrabajos({ punto_id, orden_id, estado } = {}) {
  const params = {}
  if (punto_id != null) params.punto_id = punto_id
  if (orden_id != null) params.orden_id = orden_id
  if (estado) params.estado = estado
  const { data } = await api.get('/api/impresion/trabajos', { params })
  return data
}

export async function reintentarTrabajo(id) {
  const { data } = await api.post(`/api/impresion/trabajos/${id}/reintentar`)
  return data
}

export async function estadoAgente(punto_id) {
  const params = punto_id != null ? { punto_id } : {}
  const { data } = await api.get('/api/impresion/agente/estado', { params })
  return data
}

// Error de axios -> { status, codigo, mensaje }, sin reinterpretar:
// - detail objeto {codigo, mensaje} (409 de /ticket): se exponen tal cual.
// - detail lista (422 de Pydantic): se une en un texto legible.
// - detail texto: va como mensaje.
// - sin respuesta (red caída): status null.
export function normalizarError(e) {
  const status = e?.response?.status ?? null
  const detail = e?.response?.data?.detail
  let codigo = null
  let mensaje = null
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    codigo = detail.codigo ?? null
    mensaje = detail.mensaje ?? null
  } else if (Array.isArray(detail)) {
    mensaje = detail
      .map((d) => {
        const campo = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : ''
        return campo ? `${campo}: ${d.msg}` : d.msg
      })
      .join('; ')
  } else if (typeof detail === 'string') {
    mensaje = detail
  }
  if (!mensaje) {
    mensaje = status ? `Error ${status}` : 'Sin conexión con el servidor'
  }
  return { status, codigo, mensaje }
}
