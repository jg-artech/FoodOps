// Listas de roles de impresión y cobro: copia EXACTA de las del backend, en
// un solo lugar del frontend. Si cambian allá, cambian aquí.
// La autorización real es siempre la del backend; esto solo decide qué
// botones mostrar para no ofrecer acciones que devolverían 403.

// router_impresion.py: ROLES_IMPRESION_TICKET
export const ROLES_IMPRESION_TICKET = [
  'tomador_orden', 'resp_tienda', 'gerente_punto',
  'gerente_general', 'admin',
]

// router_impresion.py: ROLES_ABRIR_CAJON (tomador_orden fuera a propósito)
export const ROLES_ABRIR_CAJON = [
  'resp_tienda', 'gerente_punto', 'gerente_general', 'admin',
]

// router_impresion.py: ROLES_ESTADO_AGENTE (indicador del agente)
export const ROLES_ESTADO_AGENTE = [
  'resp_tienda', 'gerente_punto', 'gerente_general', 'admin',
]

// router_ordenes.py: _ROLES_CONFIRMAR_COBRO. A diferencia de ROLES_CAJA
// (caja financiera/gastos/fondos), gerente_punto SÍ confirma cobros - ver
// docs/AUDITORIA_COBRO_EFECTIVO.md.
export const ROLES_CONFIRMAR_COBRO = [
  'resp_tienda', 'gerente_punto', 'gerente_general', 'admin',
]

// router_ordenes.py: _ROLES_CANCELAR_COCINA (los mismos que confirman cobros).
// Cancelan con motivo y contraseña, en cocina y en Órdenes (POS).
export const ROLES_CANCELAR_COCINA = ROLES_CONFIRMAR_COBRO

// ¿El rol de la sesión actual está en la lista?
export function tieneRol(usuario, roles) {
  return !!usuario?.rol && roles.includes(usuario.rol)
}

// _ROLES_GERENCIA (router_abastecimiento.py, router_config.py, router_caja.py...):
// reglas de abastecimiento, puntos de venta y usuarios.
export const ROLES_GERENCIA = ['gerente_general', 'admin']

// core/permisos_ordenes.py: quién cambia el estado de cocina por PUT /status.
// El repartidor solo marca entregado; el vendedor, nada.
export const ROLES_MARCAR_LISTO = [
  'cocinero', 'resp_tienda', 'gerente_punto', 'gerente_general', 'admin',
]
export const ROLES_MARCAR_ENTREGADO = ['repartidor', ...ROLES_MARCAR_LISTO]

// core/permisos_ordenes.py: ROLES_SOLO_ORDENES_DE_HOY. En el frontend, estos
// roles solo navegan por el POS (RUTAS_SOLO_POS); el resto lo bloquea el backend.
export const ROLES_SOLO_POS = ['tomador_orden']
export const RUTAS_SOLO_POS = ['/pos', '/pos/nueva-orden', '/pos/ordenes']

// router_caja.py / router_stock.py: _ROLES_TIENDA (caja, gastos, inventario).
export const ROLES_CAJA = ['resp_tienda', 'gerente_general', 'admin']

// router_abastecimiento.py: _ROLES_CENTRAL.
export const ROLES_CENTRAL = ['gerente_central', 'gerente_general', 'admin']

// core/permisos_ordenes.py: ROLES_SOLO_IMPORTES_PROPIOS. La API les oculta
// los importes de las órdenes que no tomaron ellos.
export const ROLES_SOLO_IMPORTES_PROPIOS = ['tomador_orden']

// Botón de reimprimir ticket en listados de órdenes. El vendedor solo
// reimprime las órdenes que tomó él: en las ajenas no recibe importes y el
// ticket saldría en Q0.00. Los demás roles, cualquier orden.
export function puedeReimprimir(usuario, orden) {
  if (!usuario?.rol) return false
  if (!tieneRol(usuario, ROLES_SOLO_IMPORTES_PROPIOS)) return true
  return orden?.tomada_por != null && orden.tomada_por === usuario.user_id
}

// Pantalla de inicio según el rol.
export function rutaInicio(usuario) {
  return tieneRol(usuario, ROLES_SOLO_POS) ? '/pos' : '/dashboard'
}
