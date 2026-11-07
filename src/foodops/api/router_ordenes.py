"""APIs de órdenes"""
import logging
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import (
    ROLES_TODAS_TIENDAS,
    TokenData,
    exigir_acceso_a_punto,
    exigir_punto_propio,
    get_current_user,
    requiere_rol,
    resolver_punto_id,
)
from foodops.core.config import settings
from foodops.db.models import (
    ITEM_TIPO_ENTREGA,
    ITEM_TIPO_PRODUCTO,
    NOMBRE_CARGO_ENTREGA,
    TOPE_CARGO_ENTREGA_DEFAULT,
    DatosFacturacion,
    MetodoPago,
    Orden,
    OrdenEstado,
    OrdenItem,
    PuntoVenta,
    TransaccionVenta,
    TipoVenta,
    Usuario,
)
from foodops.db.models_stock import ProductoComponente, ProductoMenu, TransaccionComponente
from foodops.domain import autorizacion_cargo
from foodops.domain.impresion import encolar_cajon_por_cobro
from foodops.api.router_auth import verificar_password_con_bloqueo
from foodops.domain.schemas import (
    CancelarCocinaRequest,
    ConfirmarCobroRequest,
    CrearTransaccionRequest,
    DatosFacturaRequest,
    OrdenCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ordenes", tags=["ordenes"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

# Roles que operan órdenes dentro de una tienda (POS, cocina, reparto).
# gerente_central queda fuera a propósito: su ámbito es el abastecimiento
# entre tiendas, no el mostrador ni la cocina.
_ROLES_OPERACION = (
    "tomador_orden",
    "cocinero",
    "repartidor",
    "resp_tienda",
    "gerente_punto",
    "gerente_general",
    "admin",
)

# Estado de cobro: eje independiente de OrdenEstado (que es de cocina - ver
# docs/AUDITORIA_COBRO_EFECTIVO.md). String simple, no Enum nativo de
# Postgres, igual que el resto de "estado" sueltos del proyecto.
ESTADO_COBRO_PENDIENTE = "pendiente_recibir"
ESTADO_COBRO_COBRADA = "cobrada"

# Puede confirmar la recepción de efectivo de una orden, y por eso también
# puede cancelar una orden ya cobrada (ver actualizar_estado_orden) - el
# vendedor no puede ninguna de las dos cosas. Mismo set de roles que
# ROLES_ABRIR_CAJON en router_impresion.py: quien confirma el cobro es quien
# dispara la apertura automática del cajón (ver confirmar_cobro_efectivo y
# docs/DISENO_IMPRESION.md §2, §7). Se mantienen como dos constantes para que
# un cambio de permisos de impresión no altere quién confirma cobros.
_ROLES_CONFIRMAR_COBRO = ("resp_tienda", "gerente_punto", "gerente_general", "admin")

# Pueden capturar datos de factura: cualquier vendedor (mismo conjunto que
# ROLES_IMPRESION_TICKET de router_impresion.py) más quien confirma cobros.
# No se importa de router_impresion porque ese módulo importa de este; una
# prueba verifica que coincidan. tomador_orden solo crea la fila (al cobrar):
# si ya existe, editarla es exclusivo de _ROLES_CONFIRMAR_COBRO.
_ROLES_CAPTURA_FACTURA = ("tomador_orden",) + _ROLES_CONFIRMAR_COBRO

_CAMPOS_FISCALES = ("requiere_factura", "nit", "nombre_fiscal", "direccion_fiscal")


def _enmascarar_nit(nit):
    """Para audit_log: solo los últimos 3 caracteres."""
    if not nit:
        return nit
    return "***" + nit[-3:]


def _datos_factura_dict(df):
    if df is None:
        return None
    return {
        "requiere_factura": df.requiere_factura,
        "nit": df.nit,
        "nombre_fiscal": df.nombre_fiscal,
        "direccion_fiscal": df.direccion_fiscal,
        "factura_generada": df.factura_generada,
        "factura_generada_por": df.factura_generada_por,
        "factura_generada_at": str(df.factura_generada_at) if df.factura_generada_at else None,
        "capturado_por": df.capturado_por,
        "capturado_at": str(df.capturado_at) if df.capturado_at else None,
        "actualizado_por": df.actualizado_por,
        "actualizado_at": str(df.actualizado_at) if df.actualizado_at else None,
    }


def _datos_factura_por_orden(session, orden_ids):
    """Una sola consulta para todas las órdenes de un listado."""
    if not orden_ids:
        return {}
    filas = session.execute(
        select(DatosFacturacion).where(DatosFacturacion.orden_id.in_(orden_ids))
    ).scalars().all()
    return {f.orden_id: _datos_factura_dict(f) for f in filas}


def _orden_dict(
    o, items, tomada_por_nombre=None, punto_nombre=None, confirmado_por_nombre=None,
    datos_factura=None,
):
    return {
        "id": o.id,
        "numero_orden": o.numero_orden,
        "estado": o.estado.value,
        "total": float(o.total),
        "cliente_nombre": o.cliente_nombre,
        "cliente_telefono": o.cliente_telefono,
        "cliente_direccion": o.cliente_direccion,
        "es_domicilio": o.es_domicilio,
        "notas_especiales": o.notas_especiales,
        "metodo_pago": o.metodo_pago.value if o.metodo_pago else None,
        "dinero_recibido": float(o.dinero_recibido) if o.dinero_recibido else None,
        "vuelto": float(o.vuelto) if o.vuelto else None,
        "created_at": str(o.created_at),
        "tomada_por": o.tomada_por,
        "tomada_por_nombre": tomada_por_nombre,
        "punto_id": o.punto_id,
        "punto_nombre": punto_nombre,
        # Eje de cobro, independiente de "estado" (cocina) - ver
        # docs/AUDITORIA_COBRO_EFECTIVO.md.
        "estado_cobro": o.estado_cobro,
        "monto_recibido": float(o.monto_recibido) if o.monto_recibido is not None else None,
        "vuelto_entregado": float(o.vuelto_entregado) if o.vuelto_entregado is not None else None,
        "confirmado_por": o.confirmado_por,
        "confirmado_por_nombre": confirmado_por_nombre,
        "confirmado_at": str(o.confirmado_at) if o.confirmado_at else None,
        # Objeto de _datos_factura_dict, o None si la orden no tiene fila
        # (equivale a requiere_factura = false).
        "datos_factura": datos_factura,
        "items": [
            {
                "producto": i.producto,
                "cantidad": i.cantidad,
                "precio_unitario": float(i.precio_unitario),
                "subtotal": float(i.subtotal),
                "especiales": i.especiales,
                # "producto" | "entrega" (cargo de entrega, migración 014).
                "tipo": i.tipo or ITEM_TIPO_PRODUCTO,
            }
            for i in items
        ],
    }


@router.post("/")
def crear_orden(
    orden: OrdenCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_OPERACION)),
):
    """Crear nueva orden. punto_id y tomada_por vienen del token, nunca del cliente."""
    session = Session()
    try:
        punto_id = exigir_punto_propio(current_user)
        # La tienda va en el número: con 3 tiendas vendiendo a la vez, un
        # sello de segundos no basta para que el número del ticket sea único.
        numero_orden = f"ORD-{punto_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Cargo de entrega (a lo sumo uno, solo en domicilio: lo valida
        # OrdenCreate). Nombre y cantidad los fija el servidor; el monto va en
        # precio_unitario.
        cargo = next((i for i in orden.items if i.tipo == ITEM_TIPO_ENTREGA), None)
        tope = None
        requiere_autorizacion = False
        if cargo is not None:
            cargo.producto = NOMBRE_CARGO_ENTREGA
            cargo.cantidad = 1
            punto_tope = session.get(PuntoVenta, punto_id)
            tope = Decimal(str(
                punto_tope.tope_cargo_entrega
                if punto_tope is not None and punto_tope.tope_cargo_entrega is not None
                else TOPE_CARGO_ENTREGA_DEFAULT
            ))
            requiere_autorizacion = (
                cargo.precio_unitario > tope and current_user.rol not in _ROLES_CONFIRMAR_COBRO
            )
            if requiere_autorizacion and not orden.autorizacion_cargo:
                raise HTTPException(
                    status_code=403,
                    detail=f"El cargo de entrega supera el tope de la tienda (Q{tope}); requiere autorización de un responsable",
                )

        # Total calculado en el servidor (incluye el cargo de entrega); el
        # cliente no manda total. Decimal para no acumular error de float.
        total = float(sum(
            (Decimal(item.cantidad) * item.precio_unitario for item in orden.items),
            Decimal("0"),
        ))

        nueva_orden = Orden(
            punto_id=punto_id,
            numero_orden=numero_orden,
            cliente_nombre=orden.cliente_nombre,
            cliente_telefono=orden.cliente_telefono,
            cliente_direccion=orden.cliente_direccion,
            metodo_pago=MetodoPago(orden.metodo_pago),
            total=total,
            es_domicilio=orden.es_domicilio,
            notas_especiales=orden.notas_especiales,
            dinero_recibido=float(orden.dinero_recibido) if orden.dinero_recibido is not None else None,
            vuelto=float(orden.vuelto) if orden.vuelto is not None else None,
            estado=OrdenEstado.PENDIENTE,
            # En efectivo, el cobro queda pendiente de que el responsable
            # confirme lo que recibió de verdad (ver confirmar_cobro_efectivo
            # más abajo). Tarjeta/transferencia se confirman al momento, no
            # hay entrega física de efectivo que esperar.
            estado_cobro=(
                ESTADO_COBRO_PENDIENTE
                if orden.metodo_pago == MetodoPago.EFECTIVO
                else ESTADO_COBRO_COBRADA
            ),
            tomada_por=current_user.user_id,
        )
        session.add(nueva_orden)
        session.flush()

        items_creados = []
        for item in orden.items:
            orden_item = OrdenItem(
                orden_id=nueva_orden.id,
                producto=item.producto,
                cantidad=item.cantidad,
                precio_unitario=float(item.precio_unitario),
                subtotal=item.cantidad * float(item.precio_unitario),
                especiales=item.especiales,
                tipo=item.tipo,
            )
            session.add(orden_item)
            items_creados.append(orden_item)

        if cargo is not None:
            # Sobre el tope: el autorizador es quien crea la orden si ya es
            # responsable, o el del token (validado y consumido aquí, en la
            # misma transacción que la orden: si algo falla, no se gasta).
            autorizado_por = None
            if cargo.precio_unitario > tope:
                if requiere_autorizacion:
                    autorizado_por = autorizacion_cargo.validar_y_consumir(
                        session,
                        orden.autorizacion_cargo,
                        punto_id=punto_id,
                        monto=cargo.precio_unitario,
                        usuario_id=current_user.user_id,
                        orden_id=nueva_orden.id,
                    )
                else:
                    autorizado_por = current_user.user_id
            # TODO(cargo de entrega): cuando exista la edición de órdenes,
            # auditar también el cambio y la eliminación del cargo, con el
            # mismo formato antes/después.
            # Decisión (2026-11-07): el repartidor recibe el dinero del cargo
            # y lo entrega al cobrador. El cargo va en el total de la orden,
            # se cobra con su mismo método de pago y se confirma junto con el
            # cobro (confirmar-cobro audita el concepto). La caja no cierra
            # con órdenes sin liquidar.
            registrar_auditoria(
                session,
                accion="CARGO_ENTREGA_REGISTRADO",
                entidad="orden",
                entidad_id=nueva_orden.id,
                usuario_id=current_user.user_id,
                punto_id=punto_id,
                detalle={
                    "numero_orden": numero_orden,
                    "antes": {"monto": None},
                    "despues": {"monto": autorizacion_cargo.monto_texto(cargo.precio_unitario)},
                    "tope_vigente": autorizacion_cargo.monto_texto(tope),
                    "sobre_tope": cargo.precio_unitario > tope,
                    "autorizado_por": autorizado_por,
                },
            )

        registrar_auditoria(
            session,
            accion="CREAR_ORDEN",
            entidad="orden",
            entidad_id=nueva_orden.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={
                "numero_orden": numero_orden,
                "total": total,
                "estado_cobro": nueva_orden.estado_cobro,
            },
        )
        session.commit()
        punto = session.get(PuntoVenta, punto_id)
        return _orden_dict(
            nueva_orden,
            items_creados,
            tomada_por_nombre=current_user.username,
            punto_nombre=punto.nombre if punto else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/")
def listar_ordenes(
    current_user: TokenData = Depends(get_current_user),
    punto_id: Optional[int] = Query(default=None),
    estado_cobro: Optional[str] = Query(default=None),
):
    """
    Listar órdenes del punto de venta del usuario autenticado.
    Solo GERENTE_GENERAL y ADMIN pueden pasar ?punto_id= para ver otra tienda,
    o quitarlo para ver todas (antes caía en silencio a la tienda propia del
    usuario en vez de "todas" - ver AUDITORIA_MULTITIENDA.md, bug reportado
    2026-10-18: el selector de "Todas las tiendas" del frontend nunca
    mostraba realmente todas, solo la tienda de casa del usuario).
    Para el resto, pedir otra tienda es 403 (antes se ignoraba en silencio).
    """
    # Este endpoint no exige rol (lo usan cocina y reparto), así que la
    # resolución general de core.auth (que trata a gerente_central como
    # "ve todas las tiendas" para efectos de abastecimiento) se quedaría
    # corta aquí: gerente_central podría leer órdenes de cualquier tienda
    # pasando ?punto_id=, que es justo el alcance que no debe tener (su
    # ámbito es abastecimiento, no el detalle de órdenes de otra tienda).
    if punto_id is not None and current_user.rol not in ROLES_TODAS_TIENDAS:
        raise HTTPException(status_code=403, detail="No autorizado para esa tienda")

    session = Session()
    try:
        effective_punto_id = resolver_punto_id(session, current_user, punto_id, permitir_todas=True)
        stmt = select(Orden).order_by(Orden.created_at.desc())
        if effective_punto_id is not None:
            stmt = stmt.where(Orden.punto_id == effective_punto_id)
        # Para la pantalla de "Cobros pendientes": pedir solo las que
        # todavía no se confirmaron, en vez de traer toda la tienda y
        # filtrar en el navegador.
        if estado_cobro is not None:
            stmt = stmt.where(Orden.estado_cobro == estado_cobro)
        ordenes = session.execute(stmt).scalars().all()

        # Mapa de nombres de tienda: con "todas las tiendas" las órdenes
        # pueden venir de cualquier punto, así que no alcanza con resolver
        # uno solo como antes.
        nombres_punto = {p.id: p.nombre for p in session.execute(select(PuntoVenta)).scalars()}

        usuario_ids = {o.tomada_por for o in ordenes if o.tomada_por}
        nombres_por_usuario = {}
        if usuario_ids:
            usuarios = session.execute(
                select(Usuario).where(Usuario.id.in_(usuario_ids))
            ).scalars().all()
            nombres_por_usuario = {u.id: (u.nombre_completo or u.username) for u in usuarios}

        datos_factura = _datos_factura_por_orden(session, [o.id for o in ordenes])

        result = []
        for o in ordenes:
            items = session.execute(
                select(OrdenItem).where(OrdenItem.orden_id == o.id)
            ).scalars().all()
            result.append(_orden_dict(
                o, items,
                tomada_por_nombre=nombres_por_usuario.get(o.tomada_por),
                punto_nombre=nombres_punto.get(o.punto_id),
                datos_factura=datos_factura.get(o.id),
            ))
        return result
    finally:
        session.close()


# TODO IMPORTANTE (riesgo, sin cambiar en este cambio): PUT /status deja que
# cualquier rol de operación (también cocinero, repartidor y vendedor)
# cancele una orden sin motivo ni contraseña, incluidas las cobradas con
# tarjeta o transferencia, y tampoco impide reactivar una orden cancelada.
# Las pantallas ya no cancelan por aquí: cocina usa
# POST /{orden_id}/cancelar-cocina y Órdenes (POS) usa POST /{orden_id}/cancelar,
# los dos con motivo y contraseña. Falta cerrar la cancelación en este
# endpoint (opción B del TODO de órdenes cobradas).
@router.put("/{orden_id}/status")
def actualizar_estado_orden(
    orden_id: int,
    data: dict,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_OPERACION)),
):
    """Actualizar estado de una orden (solo de la tienda del usuario)."""
    session = Session()
    try:
        orden = session.get(Orden, orden_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        exigir_acceso_a_punto(current_user, orden.punto_id)
        nuevo_estado = data.get("estado")
        nuevo_estado_enum = OrdenEstado(nuevo_estado)

        if nuevo_estado_enum == OrdenEstado.CANCELADO:
            # Una vez el responsable confirmó el efectivo recibido, cancelar
            # la orden deja de ser algo que el vendedor pueda hacer solo -
            # es decisión de quien maneja caja. Solo aplica a efectivo: una
            # orden con tarjeta/transferencia nace "cobrada" de inmediato
            # (ver crear_orden) y seguía pudiéndose cancelar como siempre,
            # sin este candado nuevo.
            if (
                orden.metodo_pago == MetodoPago.EFECTIVO
                and orden.estado_cobro == ESTADO_COBRO_COBRADA
                and current_user.rol not in _ROLES_CONFIRMAR_COBRO
            ):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Esta orden ya fue cobrada; solo un responsable de "
                        "tienda o gerencia puede anularla"
                    ),
                )
            registrar_auditoria(
                session,
                accion="ANULAR_ORDEN",
                entidad="orden",
                entidad_id=orden_id,
                usuario_id=current_user.user_id,
                punto_id=orden.punto_id,
                detalle={"numero_orden": orden.numero_orden, "estado_cobro": orden.estado_cobro},
            )

        orden.estado = nuevo_estado_enum

        session.commit()
        return {"id": orden.id, "numero_orden": orden.numero_orden, "estado": orden.estado.value}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {nuevo_estado}")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


# Cancelan desde cocina: los mismos que confirman cobros.
_ROLES_CANCELAR_COCINA = _ROLES_CONFIRMAR_COBRO

# Mismo mensaje y código para contraseña incorrecta y usuario bloqueado: no
# se revela si la cuenta está bloqueada. 401: el frontend exceptúa esta ruta
# de su cierre de sesión por 401 (services/api.js).
def _contrasena_incorrecta() -> HTTPException:
    return HTTPException(status_code=401, detail="Contraseña incorrecta")


def _errores_sin_input(exc: ValidationError) -> list:
    """Errores de validación sin el campo "input" de Pydantic, que en un
    campo faltante trae el cuerpo completo (con la contraseña)."""
    return [
        {"loc": ["body", *e["loc"]], "msg": e["msg"], "type": e["type"]}
        for e in exc.errors(include_url=False, include_input=False, include_context=False)
    ]


_ORIGEN_COCINA = "cocina"
_ORIGEN_POS = "pos"


def _cancelar_orden(orden_id: int, body, current_user: TokenData, *, origen: str) -> dict:
    """Cancelación con motivo y contraseña personal de quien cancela (el rol
    lo exige la dependencia del endpoint). Orden de validaciones: motivo y
    cuerpo (422) -> orden existe (404) -> tienda (403) -> ya cancelada (409)
    -> cobrada, solo en cocina (409) -> bloqueo o contraseña (401, mismo
    mensaje) -> cancelar.

    Una orden cancelada no se reactiva por aquí (no hay endpoint para eso).
    La contraseña nunca se guarda: ni en auditoría, ni en logs, ni en los
    mensajes de error.
    """
    # body sin modelo en la firma y validación a mano: el 422 sale sin "input".
    try:
        datos = CancelarCocinaRequest.model_validate(body if isinstance(body, dict) else {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_errores_sin_input(exc))

    session = Session()
    try:
        orden = session.get(Orden, orden_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        exigir_acceso_a_punto(current_user, orden.punto_id)
        if orden.estado == OrdenEstado.CANCELADO:
            raise HTTPException(status_code=409, detail="La orden ya está cancelada")
        cobrada = orden.estado_cobro == ESTADO_COBRO_COBRADA
        if cobrada and origen == _ORIGEN_COCINA:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Esta orden ya fue cobrada y no se puede cancelar desde cocina; "
                    "cancélala desde Órdenes (POS) con el motivo"
                ),
            )

        usuario = session.get(Usuario, current_user.user_id)
        resultado = (
            verificar_password_con_bloqueo(usuario, datos.password) if usuario else "password_incorrecto"
        )
        if resultado:
            # El intento cuenta en el mismo contador del login: se guarda
            # aunque la cancelación se rechace.
            registrar_auditoria(
                session,
                accion="CANCELACION_COCINA_RECHAZADA" if origen == _ORIGEN_COCINA else "CANCELACION_ORDEN_RECHAZADA",
                entidad="orden",
                entidad_id=orden.id,
                usuario_id=current_user.user_id,
                punto_id=orden.punto_id,
                detalle={
                    "numero_orden": orden.numero_orden,
                    "origen": origen,
                    "motivo_rechazo": resultado,
                    "intentos": usuario.intentos_fallidos if usuario else None,
                },
            )
            session.commit()
            raise _contrasena_incorrecta()

        estado_previo = orden.estado.value
        estado_cobro_previo = orden.estado_cobro
        cancelada_at = datetime.utcnow()
        orden.estado = OrdenEstado.CANCELADO
        # TODO: si la orden tiene datos de factura capturados y la factura no
        # está generada, quedan como están (no se borran). Falta decidir qué
        # pasa con ellos al cancelar.
        # TODO: órdenes activas antiguas (p. ej. pendientes de hace semanas):
        # falta decidir qué hacer con ellas. Este endpoint no las cancela en
        # bloque ni cambia su estado.
        detalle = {
            "orden_id": orden.id,
            "numero_orden": orden.numero_orden,
            "origen": origen,
            "estado_previo": estado_previo,
            "estado_cobro_previo": estado_cobro_previo,
            "motivo": datos.motivo,
            "cancelada_at": cancelada_at.isoformat(),
        }
        if cobrada:
            # TODO(devolución): el flujo de devolución al cliente está
            # pendiente de definir. Mientras tanto queda registrado aquí qué
            # se cobró y que la devolución está pendiente. Una orden en
            # efectivo cancelada deja de contar en el cuadre (solo cuenta
            # COBRADA y no cancelada): el dinero sale de caja al devolverlo.
            detalle.update({
                "monto_cobrado": float(orden.total),
                "metodo_pago": orden.metodo_pago.value if orden.metodo_pago else None,
                "devolucion_pendiente": True,
            })
        registrar_auditoria(
            session,
            accion="ORDEN_CANCELADA_DESDE_COCINA" if origen == _ORIGEN_COCINA else "ORDEN_CANCELADA",
            entidad="orden",
            entidad_id=orden.id,
            usuario_id=current_user.user_id,
            punto_id=orden.punto_id,
            detalle=detalle,
        )
        session.commit()
        return {
            "id": orden.id,
            "numero_orden": orden.numero_orden,
            "estado": orden.estado.value,
            "devolucion_pendiente": cobrada,
        }
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Error inesperado al cancelar la orden %s (%s)", orden_id, origen)
        raise HTTPException(status_code=500, detail="Error interno del servidor")
    finally:
        session.close()


@router.post("/{orden_id}/cancelar-cocina")
def cancelar_desde_cocina(
    orden_id: int,
    body: object = Body(None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CANCELAR_COCINA)),
):
    """Cancelar desde cocina: motivo y contraseña personal. No cancela
    órdenes cobradas (409); esas se cancelan desde el POS."""
    return _cancelar_orden(orden_id, body, current_user, origen=_ORIGEN_COCINA)


@router.post("/{orden_id}/cancelar")
def cancelar_orden(
    orden_id: int,
    body: object = Body(None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CANCELAR_COCINA)),
):
    """Cancelar desde Órdenes (POS): motivo y contraseña personal, mismos
    roles que cocina. Sí cancela órdenes cobradas: la auditoría registra el
    monto, el método y que la devolución queda pendiente.

    Decisión (2026-11-07): quien puede cancelar da siempre el motivo, y con
    más razón si la orden ya fue pagada. Esto resuelve, para el POS, la
    opción A del TODO de órdenes cobradas; cocina sigue sin cancelarlas.
    """
    return _cancelar_orden(orden_id, body, current_user, origen=_ORIGEN_POS)


def _concepto_cobro(session, orden: Orden) -> dict:
    """Desglose del total de la orden: productos y cargo de entrega."""
    cargo = session.execute(
        select(func.coalesce(func.sum(OrdenItem.subtotal), 0)).where(
            OrdenItem.orden_id == orden.id, OrdenItem.tipo == ITEM_TIPO_ENTREGA
        )
    ).scalar_one()
    cargo = round(float(cargo), 2)
    return {"productos": round(float(orden.total) - cargo, 2), "cargo_entrega": cargo}


@router.post("/{orden_id}/confirmar-cobro")
def confirmar_cobro_efectivo(
    orden_id: int,
    body: ConfirmarCobroRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CONFIRMAR_COBRO)),
):
    """El responsable confirma lo que recibió de verdad al entregar la
    orden en efectivo. Antes de esto, el dinero no entra al cuadre de caja
    (ver _calcular_efectivo_esperado en router_caja.py)."""
    session = Session()
    try:
        orden = session.get(Orden, orden_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        exigir_acceso_a_punto(current_user, orden.punto_id)

        if orden.metodo_pago != MetodoPago.EFECTIVO:
            raise HTTPException(status_code=400, detail="Esta orden no es en efectivo")
        if orden.estado == OrdenEstado.CANCELADO:
            raise HTTPException(status_code=400, detail="No se puede confirmar el cobro de una orden cancelada")
        if orden.estado_cobro == ESTADO_COBRO_COBRADA:
            raise HTTPException(status_code=400, detail="Esta orden ya fue cobrada")

        orden.monto_recibido = float(body.monto_recibido)
        orden.vuelto_entregado = float(body.vuelto_entregado)
        orden.confirmado_por = current_user.user_id
        orden.confirmado_at = datetime.utcnow()
        orden.estado_cobro = ESTADO_COBRO_COBRADA

        registrar_auditoria(
            session,
            accion="CONFIRMAR_COBRO_EFECTIVO",
            entidad="orden",
            entidad_id=orden.id,
            usuario_id=current_user.user_id,
            punto_id=orden.punto_id,
            detalle={
                "numero_orden": orden.numero_orden,
                "monto_recibido": float(body.monto_recibido),
                "vuelto_entregado": float(body.vuelto_entregado),
                "vuelto_esperado": float(orden.vuelto) if orden.vuelto is not None else None,
                # Concepto de lo recibido: productos y cargo de entrega (el
                # cargo se cobra junto con la orden, por el mismo método).
                "concepto": _concepto_cobro(session, orden),
            },
        )
        # Abre el cajón físico una sola vez por orden, solo si la tienda tiene
        # cajon_activo (docs/DISENO_IMPRESION.md §7). Nunca bloquea el cobro:
        # va en un SAVEPOINT y un fallo se descarta (§8).
        encolar_cajon_por_cobro(session, orden, current_user.user_id)
        session.commit()

        items = session.execute(select(OrdenItem).where(OrdenItem.orden_id == orden.id)).scalars().all()
        punto = session.get(PuntoVenta, orden.punto_id)
        confirmador = session.get(Usuario, current_user.user_id)
        nombre_confirmador = (
            (confirmador.nombre_completo or confirmador.username) if confirmador else None
        )
        return _orden_dict(
            orden,
            items,
            punto_nombre=punto.nombre if punto else None,
            confirmado_por_nombre=nombre_confirmador,
            datos_factura=_datos_factura_por_orden(session, [orden.id]).get(orden.id),
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


def _cargar_orden_para_factura(session, orden_id: int, current_user: TokenData):
    """Orden bloqueada (FOR UPDATE) + control de tienda. La fila de datos
    fiscales también se bloquea, para que "marcar generada" y una edición
    simultánea no se crucen."""
    orden = session.get(Orden, orden_id, with_for_update=True)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    exigir_acceso_a_punto(current_user, orden.punto_id)
    df = session.execute(
        select(DatosFacturacion).where(DatosFacturacion.orden_id == orden_id).with_for_update()
    ).scalar_one_or_none()
    return orden, df


@router.put("/{orden_id}/datos-factura")
def guardar_datos_factura(
    orden_id: int,
    body: DatosFacturaRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CAPTURA_FACTURA)),
):
    """Captura o edita los datos fiscales de una orden. No emite factura.

    - Vendedor (tomador_orden): solo crea la fila, al cobrar. Si ya existe, 403.
    - Cobrador (_ROLES_CONFIRMAR_COBRO): edita mientras la factura no esté
      marcada como generada.
    - 409 para cualquier rol si la factura ya se generó o la orden está
      cancelada.
    """
    session = Session()
    try:
        orden, df = _cargar_orden_para_factura(session, orden_id, current_user)
        if orden.estado == OrdenEstado.CANCELADO:
            raise HTTPException(status_code=409, detail="La orden está cancelada; no se pueden cambiar sus datos de factura")
        if df is not None and df.factura_generada:
            raise HTTPException(status_code=409, detail="La factura ya fue generada; los datos fiscales están bloqueados")
        if df is not None and current_user.rol not in _ROLES_CONFIRMAR_COBRO:
            raise HTTPException(
                status_code=403,
                detail="Los datos de factura ya fueron capturados; solo un responsable puede editarlos",
            )

        nuevos = {c: getattr(body, c) for c in _CAMPOS_FISCALES}
        ahora = datetime.utcnow()
        if df is None:
            antes_vals = {c: None for c in _CAMPOS_FISCALES}
            df = DatosFacturacion(
                orden_id=orden.id,
                capturado_por=current_user.user_id,
                capturado_at=ahora,
                **nuevos,
            )
            session.add(df)
            cambiados = [c for c in _CAMPOS_FISCALES if nuevos[c] is not None]
        else:
            antes_vals = {c: getattr(df, c) for c in _CAMPOS_FISCALES}
            cambiados = [c for c in _CAMPOS_FISCALES if nuevos[c] != antes_vals[c]]
            if cambiados:
                for c in cambiados:
                    setattr(df, c, nuevos[c])
                df.actualizado_por = current_user.user_id
                df.actualizado_at = ahora

        if cambiados:
            def _para_log(campo, valor):
                return _enmascarar_nit(valor) if campo == "nit" else valor

            registrar_auditoria(
                session,
                accion="DATOS_FACTURA_ACTUALIZADOS",
                entidad="orden",
                entidad_id=orden.id,
                usuario_id=current_user.user_id,
                punto_id=orden.punto_id,
                detalle={
                    "numero_orden": orden.numero_orden,
                    "antes": {c: _para_log(c, antes_vals[c]) for c in cambiados},
                    "despues": {c: _para_log(c, nuevos[c]) for c in cambiados},
                },
            )
        session.commit()
        return _datos_factura_dict(df)
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        # Dos capturas simultáneas de la misma orden: gana la primera.
        session.rollback()
        raise HTTPException(status_code=409, detail="Los datos de factura de esta orden ya fueron capturados")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.post("/{orden_id}/datos-factura/marcar-generada")
def marcar_factura_generada(
    orden_id: int,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CONFIRMAR_COBRO)),
):
    """El cobrador indica que ya hizo la factura (manual). No guarda número
    de factura. Después de esto los datos fiscales quedan bloqueados."""
    session = Session()
    try:
        orden, df = _cargar_orden_para_factura(session, orden_id, current_user)
        if orden.estado == OrdenEstado.CANCELADO:
            raise HTTPException(status_code=409, detail="La orden está cancelada")
        if orden.estado_cobro != ESTADO_COBRO_COBRADA:
            raise HTTPException(status_code=409, detail="La orden todavía no está cobrada")
        if df is None or not df.requiere_factura:
            raise HTTPException(status_code=422, detail="Esta orden no requiere factura")
        if df.factura_generada:
            raise HTTPException(status_code=409, detail="La factura ya estaba marcada como generada")

        df.factura_generada = True
        df.factura_generada_por = current_user.user_id
        df.factura_generada_at = datetime.utcnow()
        registrar_auditoria(
            session,
            accion="FACTURA_MARCADA_GENERADA",
            entidad="orden",
            entidad_id=orden.id,
            usuario_id=current_user.user_id,
            punto_id=orden.punto_id,
            detalle={"numero_orden": orden.numero_orden, "nit": _enmascarar_nit(df.nit)},
        )
        session.commit()
        return _datos_factura_dict(df)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/reporte/{punto_id}")
def reporte_cierre(
    punto_id: int,
    current_user: TokenData = Depends(
        requiere_rol("admin", "gerente_general", "gerente_punto")
    ),
):
    """Reporte de cierre del día."""
    session = Session()
    try:
        resolver_punto_id(session, current_user, punto_id)
        today = date.today()
        today_start = datetime(today.year, today.month, today.day)

        ordenes = session.execute(
            select(Orden).where(
                Orden.punto_id == punto_id,
                Orden.created_at >= today_start,
                Orden.estado != OrdenEstado.CANCELADO,
            )
        ).scalars().all()

        total_dinero = sum(float(o.total) for o in ordenes)
        por_metodo = {"efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0}
        for o in ordenes:
            if o.metodo_pago:
                por_metodo[o.metodo_pago.value] = por_metodo.get(o.metodo_pago.value, 0.0) + float(o.total)

        producto_counter: Counter = Counter()
        for o in ordenes:
            items = session.execute(select(OrdenItem).where(OrdenItem.orden_id == o.id)).scalars().all()
            for item in items:
                # El cargo de entrega no es un producto vendido.
                if item.tipo == ITEM_TIPO_ENTREGA:
                    continue
                producto_counter[item.producto] += item.cantidad

        total_efectivo_recibido = sum(
            float(o.dinero_recibido) for o in ordenes
            if o.dinero_recibido and o.metodo_pago and o.metodo_pago.value == "efectivo"
        )
        total_vuelto_dado = sum(
            float(o.vuelto) for o in ordenes
            if o.vuelto and o.metodo_pago and o.metodo_pago.value == "efectivo"
        )

        return {
            "fecha": str(today),
            "total_ordenes": len(ordenes),
            "total_dinero": round(total_dinero, 2),
            "por_metodo_pago": por_metodo,
            "efectivo_recibido": round(total_efectivo_recibido, 2),
            "vuelto_dado": round(total_vuelto_dado, 2),
            "top_productos": [
                {"producto": p, "cantidad": c} for p, c in producto_counter.most_common(5)
            ],
        }
    finally:
        session.close()


def _validar_componentes_grupo(componentes, elegidos: Counter) -> None:
    """Valida que la cantidad de opciones elegidas por grupo_elegible esté
    dentro de [cantidad_elegible_minima, cantidad_elegible_maxima]. `elegidos`
    es un Counter (item_inventario_id -> veces elegido) para permitir repetir
    la misma opción varias veces (p.ej. 2x Arroz de las 3 guarniciones que
    permite el combo) - cada repetición cuenta contra el máximo del grupo.
    Grupos legacy sin grupo_elegible formal no se validan aquí (no hay regla
    que aplicar)."""
    grupos: dict = {}
    for c in componentes:
        if c.grupo_elegible is None:
            continue
        grupo = grupos.setdefault(
            c.grupo_elegible,
            {
                "nombre": c.nombre_grupo or f"Grupo {c.grupo_elegible}",
                "min": c.cantidad_elegible_minima,
                "max": c.cantidad_elegible_maxima,
                "item_ids": set(),
            },
        )
        grupo["item_ids"].add(c.item_inventario_id)

    for grupo in grupos.values():
        cantidad_elegida = sum(elegidos[iid] for iid in grupo["item_ids"])
        if cantidad_elegida < grupo["min"]:
            raise HTTPException(
                status_code=400,
                detail=f"{grupo['nombre']}: debes elegir mín. {grupo['min']} opción(es)",
            )
        if cantidad_elegida > grupo["max"]:
            raise HTTPException(
                status_code=400,
                detail=f"{grupo['nombre']}: máximo {grupo['max']} opción(es)",
            )


def _registrar_componentes_transaccion(session, transaccion_id: int, items) -> None:
    """Para cada item vendido con producto_menu_id, expande su receta
    (producto_componentes) y registra el consumo exacto por componente.

    Los componentes marcados elegible=True (p.ej. la guarnición a elegir dentro de
    un combo) solo se registran si el cliente frontend indicó explícitamente cuál
    eligió vía item.componentes_elegidos (lista de item_inventario_id). Sin esa
    lista, se omiten (no hay dato real que registrar para esos slots).
    """
    producto_ids = [item.producto_menu_id for item in items if item.producto_menu_id]
    if not producto_ids:
        return

    productos = {
        p.id: p
        for p in session.execute(
            select(ProductoMenu).where(ProductoMenu.id.in_(producto_ids))
        ).scalars().all()
    }
    componentes_por_producto: dict = {}
    for c in session.execute(
        select(ProductoComponente).where(ProductoComponente.producto_menu_id.in_(producto_ids))
    ).scalars().all():
        componentes_por_producto.setdefault(c.producto_menu_id, []).append(c)

    for item in items:
        if not item.producto_menu_id:
            continue
        producto = productos.get(item.producto_menu_id)
        if not producto:
            continue
        tipo_origen_base = "combo" if producto.tipo == "combo" else "producto_individual"
        elegidos = Counter(item.componentes_elegidos or [])
        componentes_producto = componentes_por_producto.get(item.producto_menu_id, [])
        _validar_componentes_grupo(componentes_producto, elegidos)
        for componente in componentes_producto:
            veces_elegido = elegidos[componente.item_inventario_id]
            if componente.elegible and veces_elegido == 0:
                continue
            # Componentes fijos se consumen una vez por unidad vendida; los
            # elegibles se multiplican también por cuántas veces se repitió esa
            # misma opción dentro del grupo (p.ej. 2x Arroz de las 3 guarniciones).
            multiplicador = veces_elegido if componente.elegible else 1
            tipo_origen = "componente_elegible" if componente.elegible else tipo_origen_base
            session.add(
                TransaccionComponente(
                    transaccion_id=transaccion_id,
                    item_inventario_id=componente.item_inventario_id,
                    cantidad=float(componente.cantidad) * item.cantidad * multiplicador,
                    tipo_origen=tipo_origen,
                )
            )


@router.post("/transacciones/")
def crear_transaccion(
    req: CrearTransaccionRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_OPERACION)),
):
    """Registrar transacción financiera con datos de costo y margen."""
    session = Session()
    try:
        punto_id = exigir_punto_propio(current_user)

        # Todo cobro en efectivo tiene que venir de una orden ya creada
        # (PENDIENTE_RECIBIR hasta que el responsable confirme, ver
        # confirmar_cobro_efectivo) - sin esto, cualquier rol de
        # _ROLES_OPERACION podía crear una TransaccionVenta en efectivo sin
        # orden asociada, y _calcular_efectivo_esperado() la contaba de
        # inmediato sin que nadie confirmara haber recibido el dinero
        # (hotfix: ver docs/AUDITORIA_COBRO_EFECTIVO.md, reproducido en la
        # revisión del 2026-10-18 con una transacción de Q777 sin orden_id).
        # Tarjeta/transferencia sin orden_id no cambian: no hay recepción
        # física de efectivo que confirmar en esos métodos.
        if req.metodo_pago == MetodoPago.EFECTIVO and req.orden_id is None:
            raise HTTPException(
                status_code=400,
                detail="Un cobro en efectivo debe registrarse como orden primero (POST /api/ordenes/)",
            )

        # orden_id viene del cliente: sin esto se podría colgar una venta de
        # esta tienda de una orden de otra.
        precio_venta = req.precio_venta
        costo_total = req.costo_total
        margen_bruto = req.margen_bruto
        margen_pct = req.margen_pct
        if req.orden_id is not None:
            orden = session.get(Orden, req.orden_id)
            if orden is None:
                raise HTTPException(status_code=404, detail="Orden no encontrada")
            if orden.punto_id != punto_id:
                raise HTTPException(status_code=403, detail="Esa orden pertenece a otra tienda")
            # El cuadre de caja suma precio_venta (_calcular_efectivo_esperado
            # en router_caja.py): con orden, el monto es el total que calculó
            # el servidor al crearla (incluye el cargo de entrega), nunca el
            # que manda el cliente. Costo y margen también se calculan aquí,
            # desde los ítems.
            # TODO(costos): el costo unitario sigue llegando del navegador
            # (ConfigView lo guarda en localStorage); la base no tiene costos
            # por producto. El cargo de entrega no va en los ítems: costo 0.
            precio_venta = float(orden.total)
            costo_total = round(sum(i.costo_unitario * i.cantidad for i in req.items), 2)
            margen_bruto = round(precio_venta - costo_total, 2)
            margen_pct = round(margen_bruto / precio_venta * 100) if precio_venta > 0 else 0

        t = TransaccionVenta(
            punto_id=punto_id,
            orden_id=req.orden_id,
            tipo_venta=TipoVenta(req.tipo_venta),
            nombre_iniciativa=req.nombre_iniciativa,
            cliente_nombre=req.cliente_nombre,
            cliente_telefono=req.cliente_telefono,
            cliente_direccion=req.cliente_direccion,
            tipo_cliente=req.tipo_cliente,
            precio_venta=precio_venta,
            costo_total=costo_total,
            margen_bruto=margen_bruto,
            margen_pct=margen_pct,
            metodo_pago=req.metodo_pago,
            items_json=[item.model_dump() for item in req.items],
            requerimientos_especiales=req.requerimientos_especiales,
            estado="completada",
        )
        session.add(t)
        session.flush()

        _registrar_componentes_transaccion(session, t.id, req.items)

        registrar_auditoria(
            session,
            accion="CREAR_TRANSACCION",
            entidad="transacciones_venta",
            entidad_id=t.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={
                "metodo_pago": req.metodo_pago,
                "total": precio_venta,
                # Lo que mandó el cliente, si difiere del total del servidor.
                "precio_venta_cliente": req.precio_venta if req.precio_venta != precio_venta else None,
            },
        )
        session.commit()
        return {"id_transaccion": t.id, "status": "creada"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/reporte-rentabilidad/{punto_id}")
def reporte_rentabilidad(
    punto_id: int,
    current_user: TokenData = Depends(
        requiere_rol("admin", "gerente_general", "gerente_punto")
    ),
):
    """Análisis de rentabilidad del día actual."""
    session = Session()
    try:
        resolver_punto_id(session, current_user, punto_id)
        today_start = datetime(date.today().year, date.today().month, date.today().day)

        transacciones = session.execute(
            select(TransaccionVenta).where(
                TransaccionVenta.punto_id == punto_id,
                TransaccionVenta.created_at >= today_start,
                TransaccionVenta.estado == "completada",
            )
        ).scalars().all()

        if not transacciones:
            return {
                "total_ordenes": 0,
                "total_venta": 0,
                "total_costo": 0,
                "margen_total": 0,
                "margen_promedio_pct": 0,
                "por_tipo_venta": [],
                "por_metodo_pago": {},
                "top_productos": [],
                "tiene_costos": False,
            }

        total_venta = sum(t.precio_venta for t in transacciones)
        total_costo = sum(t.costo_total for t in transacciones)
        margen_total = total_venta - total_costo
        margen_pct = round((margen_total / total_venta * 100) if total_venta else 0, 2)
        tiene_costos = total_costo > 0

        por_tipo: dict = {}
        for t in transacciones:
            tipo = t.tipo_venta.value if hasattr(t.tipo_venta, "value") else str(t.tipo_venta)
            if tipo not in por_tipo:
                por_tipo[tipo] = {"tipo_venta": tipo, "cantidad": 0, "total_venta": 0, "margen_total": 0}
            por_tipo[tipo]["cantidad"] += 1
            por_tipo[tipo]["total_venta"] += t.precio_venta
            por_tipo[tipo]["margen_total"] += t.margen_bruto

        por_metodo: dict = {"efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0}
        for t in transacciones:
            if t.metodo_pago in por_metodo:
                por_metodo[t.metodo_pago] += t.precio_venta

        producto_counter: Counter = Counter()
        for t in transacciones:
            items = t.items_json or []
            for item in items:
                nombre = item.get("nombre", "")
                cantidad = item.get("cantidad", 1)
                producto_counter[nombre] += cantidad

        return {
            "total_ordenes": len(transacciones),
            "total_venta": round(total_venta, 2),
            "total_costo": round(total_costo, 2),
            "margen_total": round(margen_total, 2),
            "margen_promedio_pct": margen_pct,
            "por_tipo_venta": list(por_tipo.values()),
            "por_metodo_pago": {k: round(v, 2) for k, v in por_metodo.items()},
            "top_productos": [
                {"producto": p, "cantidad": c} for p, c in producto_counter.most_common(10)
            ],
            "tiene_costos": tiene_costos,
        }
    finally:
        session.close()
