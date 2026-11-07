// Cargo de entrega en órdenes a domicilio (migración 014).
//
// El backend es quien decide: valida el monto, fija nombre y cantidad, suma
// el cargo al total y exige la autorización de un responsable sobre el tope
// de la tienda. Aquí solo se replica para avisar antes de enviar.

export const TIPO_ENTREGA = 'entrega'
export const NOMBRE_CARGO_ENTREGA = 'Cargo de entrega'

export const esCargoEntrega = (item) => item?.tipo === TIPO_ENTREGA
export const itemsSinCargo = (items) => (items || []).filter((i) => !esCargoEntrega(i))
export const cargoDe = (items) => (items || []).find(esCargoEntrega) || null

// Mismo formato que el Precio del backend: >= 0 y hasta 2 decimales.
const MONTO_REGEX = /^\d{1,8}(\.\d{1,2})?$/
export const MSG_CARGO_INVALIDO = 'El cargo de entrega debe ser un monto de Q0.00 en adelante, con hasta 2 decimales'

export function errorCargoEntrega(valor) {
  const s = String(valor ?? '').trim()
  if (!s) return ''
  return MONTO_REGEX.test(s) ? '' : MSG_CARGO_INVALIDO
}

// Monto en número (0 si está vacío o es inválido).
export function montoCargo(valor) {
  const s = String(valor ?? '').trim()
  return s && MONTO_REGEX.test(s) ? Number(s) : 0
}

// Texto canónico con 2 decimales, igual al del token ("250.00").
export const montoTexto = (monto) => Number(monto).toFixed(2)

// En centavos para no comparar floats. Tope desconocido: no se avisa (el
// backend igual responde 403 y la pantalla pide la autorización entonces).
export function superaTope(monto, tope) {
  if (tope === null || tope === undefined || tope === '') return false
  return Math.round(Number(monto) * 100) > Math.round(Number(tope) * 100)
}

export const VIGENCIA_AUTORIZACION_MS = 5 * 60 * 1000

// La autorización sirve si es por el monto exacto y no ha vencido.
export function autorizacionVigente(autorizacion, monto, ahora = Date.now()) {
  return !!autorizacion
    && autorizacion.monto === montoTexto(monto)
    && ahora < autorizacion.expiraLocal
}

// Estado vacío del cargo en la pantalla de nueva orden.
export const cargoEntregaVacio = () => ({ monto: '', autorizacion: null })
