"""APIs de órdenes"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from collections import Counter

from foodops.domain.schemas import OrdenCreate
from foodops.db.models import Orden, OrdenItem, OrdenEstado, MetodoPago
from foodops.core.config import settings

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
def crear_orden(orden: OrdenCreate):
    """Crear nueva orden"""
    session = Session()
    try:
        numero_orden = f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        total = sum(item.cantidad * item.precio_unitario for item in orden.items) if orden.items else 0.0

        nueva_orden = Orden(
            punto_id=2,
            numero_orden=numero_orden,
            cliente_nombre=orden.cliente_nombre,
            cliente_telefono=orden.cliente_telefono,
            cliente_direccion=orden.cliente_direccion,
            metodo_pago=MetodoPago(orden.metodo_pago),
            total=total,
            es_domicilio=orden.es_domicilio,
            notas_especiales=orden.notas_especiales,
            estado=OrdenEstado.PENDIENTE,
        )
        session.add(nueva_orden)
        session.flush()

        items_creados = []
        for item in orden.items:
            orden_item = OrdenItem(
                orden_id=nueva_orden.id,
                producto=item.producto,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                subtotal=item.cantidad * item.precio_unitario,
                especiales=item.especiales,
            )
            session.add(orden_item)
            items_creados.append(orden_item)

        session.commit()
        return _orden_dict(nueva_orden, items_creados)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.put("/{orden_id}/status")
def actualizar_estado_orden(orden_id: int, data: dict):
    """Actualizar estado de una orden"""
    session = Session()
    try:
        orden = session.get(Orden, orden_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        nuevo_estado = data.get("estado")
        orden.estado = OrdenEstado(nuevo_estado)
        session.commit()
        return {"id": orden.id, "numero_orden": orden.numero_orden, "estado": orden.estado.value}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {nuevo_estado}")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/reporte/{punto_id}")
def reporte_cierre(punto_id: int):
    """Reporte de cierre del día"""
    session = Session()
    try:
        from datetime import date
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

        producto_counter = Counter()
        for o in ordenes:
            items = session.execute(select(OrdenItem).where(OrdenItem.orden_id == o.id)).scalars().all()
            for item in items:
                producto_counter[item.producto] += item.cantidad

        return {
            "fecha": str(today),
            "total_ordenes": len(ordenes),
            "total_dinero": round(total_dinero, 2),
            "por_metodo_pago": por_metodo,
            "top_productos": [{"producto": p, "cantidad": c} for p, c in producto_counter.most_common(5)],
        }
    finally:
        session.close()


@router.get("/{punto_id}")
def listar_ordenes(punto_id: int):
    """Listar órdenes por punto de venta con sus items"""
    session = Session()
    try:
        ordenes = session.execute(
            select(Orden).where(Orden.punto_id == punto_id).order_by(Orden.created_at.desc())
        ).scalars().all()
        result = []
        for o in ordenes:
            items = session.execute(select(OrdenItem).where(OrdenItem.orden_id == o.id)).scalars().all()
            result.append(_orden_dict(o, items))
        return result
    finally:
        session.close()
