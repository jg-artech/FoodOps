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

// ¿El rol de la sesión actual está en la lista?
export function tieneRol(usuario, roles) {
  return !!usuario?.rol && roles.includes(usuario.rol)
}
