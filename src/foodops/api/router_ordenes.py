"""APIs de órdenes"""
import logging
from collections import Counter
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import TokenData, get_current_user, requiere_rol
from foodops.core.config import settings
from foodops.db.models import (
    MetodoPago,
    Orden,
    OrdenEstado,
    OrdenItem,
    TransaccionVenta,
    TipoVenta,
)
from foodops.domain.schemas import CrearTransaccionRequest, OrdenCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ordenes", tags=["ordenes"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)


def _orden_dict(o, items):
    return {
        "id": o.id,
        "numero_orden": o.numero_orden,
        "estado": o.estado.value,
        "total": float(o.total),
        "cliente_nombre": o.cliente_nombre,
        "cliente_telefono": o.cliente_telefono,
        "cliente_direccion": o.cliente_direccion,
        "es_domicilio": o.es_domicilio,
        "metodo_pago": o.metodo_pago.value if o.metodo_pago else None,
        "dinero_recibido": float(o.dinero_recibido) if o.dinero_recibido else None,
        "vuelto": float(o.vuelto) if o.vuelto else None,
        "created_at": str(o.created_at),
        "items": [
            {
                "producto": i.producto,
                "cantidad": i.cantidad,
                "precio_unitario": float(i.precio_unitario),
                "subtotal": float(i.subtotal),
                "especiales": i.especiales,
            }
            for i in items
        ],
    }


@router.post("/")
def crear_orden(
    orden: OrdenCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Crear nueva orden. punto_id y tomada_por vienen del token, nunca del cliente."""
    session = Session()
    try:
        numero_orden = f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        # Total calculated server-side from item quantities; subtotals are recalculated too
        total = sum(
            item.cantidad * float(item.precio_unitario) for item in orden.items
        ) if orden.items else 0.0

        nueva_orden = Orden(
            punto_id=current_user.punto_id,
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
            )
            session.add(orden_item)
            items_creados.append(orden_item)

        registrar_auditoria(
            session,
            accion="CREAR_ORDEN",
            entidad="orden",
            entidad_id=nueva_orden.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"numero_orden": numero_orden, "total": total},
        )
        session.commit()
        return _orden_dict(nueva_orden, items_creados)
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
):
    """
    Listar órdenes del punto de venta del usuario autenticado.
    Solo GERENTE_GENERAL y ADMIN pueden pasar ?punto_id= para ver otra tienda.
    """
    _ROLES_MULTI_PUNTO = ("gerente_general", "admin")

    if punto_id is not None and current_user.rol not in _ROLES_MULTI_PUNTO:
        punto_id = None  # silently ignore; use the user's own punto

    effective_punto_id = punto_id if punto_id is not None else current_user.punto_id

    session = Session()
    try:
        ordenes = session.execute(
            select(Orden)
            .where(Orden.punto_id == effective_punto_id)
            .order_by(Orden.created_at.desc())
        ).scalars().all()
        result = []
        for o in ordenes:
            items = session.execute(
                select(OrdenItem).where(OrdenItem.orden_id == o.id)
            ).scalars().all()
            result.append(_orden_dict(o, items))
        return result
    finally:
        session.close()


@router.put("/{orden_id}/status")
def actualizar_estado_orden(
    orden_id: int,
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Actualizar estado de una orden."""
    session = Session()
    try:
        orden = session.get(Orden, orden_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        nuevo_estado = data.get("estado")
        orden.estado = OrdenEstado(nuevo_estado)

        if OrdenEstado(nuevo_estado) == OrdenEstado.CANCELADO:
            registrar_auditoria(
                session,
                accion="ANULAR_ORDEN",
                entidad="orden",
                entidad_id=orden_id,
                usuario_id=current_user.user_id,
                punto_id=orden.punto_id,
                detalle={"numero_orden": orden.numero_orden},
            )

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


@router.get("/reporte/{punto_id}")
def reporte_cierre(
    punto_id: int,
    current_user: TokenData = Depends(
        requiere_rol("admin", "gerente_general", "gerente_punto")
    ),
):
    """Reporte de cierre del día."""
    _ROLES_MULTI_PUNTO = ("gerente_general", "admin")
    if current_user.rol not in _ROLES_MULTI_PUNTO and punto_id != current_user.punto_id:
        raise HTTPException(status_code=403, detail="No autorizado para este punto de venta")

    session = Session()
    try:
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


@router.post("/transacciones/")
def crear_transaccion(
    req: CrearTransaccionRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Registrar transacción financiera con datos de costo y margen."""
    session = Session()
    try:
        t = TransaccionVenta(
            punto_id=current_user.punto_id,
            orden_id=req.orden_id,
            tipo_venta=TipoVenta(req.tipo_venta),
            nombre_iniciativa=req.nombre_iniciativa,
            cliente_nombre=req.cliente_nombre,
            cliente_telefono=req.cliente_telefono,
            cliente_direccion=req.cliente_direccion,
            tipo_cliente=req.tipo_cliente,
            precio_venta=req.precio_venta,
            costo_total=req.costo_total,
            margen_bruto=req.margen_bruto,
            margen_pct=req.margen_pct,
            metodo_pago=req.metodo_pago,
            items_json=[item.model_dump() for item in req.items],
            requerimientos_especiales=req.requerimientos_especiales,
            estado="completada",
        )
        session.add(t)
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
    _ROLES_MULTI_PUNTO = ("gerente_general", "admin")
    if current_user.rol not in _ROLES_MULTI_PUNTO and punto_id != current_user.punto_id:
        raise HTTPException(status_code=403, detail="No autorizado para este punto de venta")

    session = Session()
    try:
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
