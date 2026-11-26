"""Permisos por acción sobre órdenes: única fuente de verdad.

Cada constante responde a "¿quién puede hacer ESTA acción?", no a "¿quién
opera la tienda?". El frontend tiene una copia en foodops-web/src/permisos.js
(solo para decidir qué mostrar); la autorización real es esta.

tomador_orden (vendedor) no está en ninguna de las listas de cambio de
estado ni de cancelación: registra órdenes y cobros, y nada más.
"""

# Pasar una orden a preparando o listo (y devolverla a pendiente): cocina y
# superiores.
ROLES_MARCAR_LISTO = (
    "cocinero",
    "resp_tienda",
    "gerente_punto",
    "gerente_general",
    "admin",
)

# Pasar una orden a entregado: además de cocina y superiores, el repartidor
# (sin él no se cierra el flujo de entrega). El repartidor no marca listo.
ROLES_MARCAR_ENTREGADO = ("repartidor",) + ROLES_MARCAR_LISTO

# Cualquier cambio de estado por PUT /api/ordenes/{id}/status. Quien no esté
# aquí recibe 403 antes de mirar la transición pedida.
ROLES_CAMBIAR_ESTADO_COCINA = ROLES_MARCAR_ENTREGADO

# Cancelar una orden (POST /cancelar-cocina y POST /cancelar, con motivo y
# contraseña). Son los mismos que confirman cobros en efectivo.
ROLES_CANCELAR = ("resp_tienda", "gerente_punto", "gerente_general", "admin")

# Roles cuyo listado de órdenes y de trabajos de impresión se limita a su
# tienda y al día de hoy (hora de Guatemala), sin parámetro que lo cambie.
ROLES_SOLO_ORDENES_DE_HOY = ("tomador_orden",)

# Roles que en el listado de órdenes solo ven el importe (total) de las
# órdenes que ellos mismos tomaron; en las demás de su tienda, total = null y
# total_oculto = true. Evita que el vendedor reconstruya el total del día.
ROLES_SOLO_IMPORTES_PROPIOS = ("tomador_orden",)

# Responsable de preparar la orden en cocina (PUT /responsable-cocina).
# Sin vínculo entre usuario y personal (decisión del 2026-11-25): el cocinero
# elige a cualquier persona activa de su tienda, pero solo si la orden aún no
# tiene responsable. Cambiar un responsable ya asignado es de gerencia.
ROLES_ASIGNAR_RESPONSABLE = ROLES_MARCAR_LISTO
ROLES_REASIGNAR_RESPONSABLE = ("resp_tienda", "gerente_punto", "gerente_general", "admin")

# Personal de cocina (/api/config/personal-cocina): lo administra el
# responsable de su tienda, y gerencia en cualquiera. Cocina lo lee para el
# selector de responsable.
ROLES_ADMINISTRAR_PERSONAL_COCINA = ("resp_tienda", "gerente_general", "admin")
ROLES_VER_PERSONAL_COCINA = ROLES_ASIGNAR_RESPONSABLE
