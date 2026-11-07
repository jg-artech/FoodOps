// Reglas de nombre del cliente y datos fiscales, copia de las del backend
// (src/foodops/domain/schemas.py). Aquí solo sirven para avisar al usuario;
// quien rechaza de verdad es el backend.

export const MSG_CLIENTE_NOMBRE = 'El nombre del cliente es obligatorio (al menos 2 letras o números)'
export const CLIENTE_NOMBRE_MAX = 100

// Espacios sobrantes fuera, igual que el backend.
export function limpiarNombre(valor) {
  return String(valor ?? '').split(/\s+/).filter(Boolean).join(' ')
}

// '' si el nombre sirve; si no, el mensaje a mostrar.
export function errorNombreCliente(valor) {
  const limpio = limpiarNombre(valor)
  const utiles = (limpio.match(/[\p{L}\p{N}]/gu) || []).length
  if (utiles < 2) return MSG_CLIENTE_NOMBRE
  if (limpio.length > CLIENTE_NOMBRE_MAX) {
    return `El nombre del cliente admite como máximo ${CLIENTE_NOMBRE_MAX} caracteres`
  }
  return ''
}

// NIT: dígitos, con guion opcional y dígito verificador 0-9 o K.
// TODO(facturación): decidir si "CF" (consumidor final) es válido. Hoy no.
export const NIT_REGEX = /^\d+(-?[0-9K])?$/
export const NIT_MAX = 20
export const MSG_NIT_INVALIDO =
  'NIT inválido: use solo dígitos, con guion y dígito verificador opcionales (ej. 1234567-8 o 1234567-K)'

export function normalizarNit(valor) {
  return String(valor ?? '').trim().toUpperCase()
}

// Datos vacíos para el formulario de factura.
export function datosFacturaVacios() {
  return { requiere_factura: false, nit: '', nombre_fiscal: '', direccion_fiscal: '' }
}

// Copia editable a partir de lo que devuelve el backend (o null).
export function datosFacturaDesde(df) {
  if (!df) return datosFacturaVacios()
  return {
    requiere_factura: !!df.requiere_factura,
    nit: df.nit || '',
    nombre_fiscal: df.nombre_fiscal || '',
    direccion_fiscal: df.direccion_fiscal || '',
  }
}

// '' si se puede guardar; si no, el primer error a mostrar.
export function errorDatosFactura(datos) {
  if (!datos?.requiere_factura) return ''
  const nit = normalizarNit(datos.nit)
  if (!nit) return 'El NIT es obligatorio cuando se requiere factura'
  if (nit.length > NIT_MAX || !NIT_REGEX.test(nit)) return MSG_NIT_INVALIDO
  if (!limpiarNombre(datos.nombre_fiscal)) return 'El nombre fiscal es obligatorio cuando se requiere factura'
  if (!limpiarNombre(datos.direccion_fiscal)) return 'La dirección fiscal es obligatoria cuando se requiere factura'
  return ''
}

// Body del PUT /api/ordenes/{id}/datos-factura. Sin factura no se mandan
// los campos (el backend los dejaría en NULL de todas formas).
export function bodyDatosFactura(datos) {
  if (!datos.requiere_factura) return { requiere_factura: false }
  return {
    requiere_factura: true,
    nit: normalizarNit(datos.nit),
    nombre_fiscal: limpiarNombre(datos.nombre_fiscal),
    direccion_fiscal: limpiarNombre(datos.direccion_fiscal),
  }
}

// Estado de factura de una orden: 'sin' | 'pendiente' | 'generada'.
export function estadoFactura(df) {
  if (!df || !df.requiere_factura) return 'sin'
  return df.factura_generada ? 'generada' : 'pendiente'
}

export const ETIQUETA_ESTADO_FACTURA = {
  sin: 'Sin factura',
  pendiente: 'Factura pendiente de generar',
  generada: 'Factura generada',
}
