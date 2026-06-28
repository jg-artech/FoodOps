"""APIs de órdenes"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date
from collections import Counter

from foodops.domain.schemas import OrdenCreate, CrearTransaccionRequest
from foodops.db.models import Orden, OrdenItem, OrdenEstado, MetodoPago, TransaccionVenta, TipoVenta
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
            dinero_recibido=orden.dinero_recibido,
            vuelto=orden.vuelto,
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
            "top_productos": [{"producto": p, "cantidad": c} for p, c in producto_counter.most_common(5)],
        }
    finally:
        session.close()


@router.post("/transacciones/")
def crear_transaccion(req: CrearTransaccionRequest):
    """Registrar transacción financiera con datos de costo y margen"""
    session = Session()
    try:
        t = TransaccionVenta(
            punto_id=req.punto_id,
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
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/reporte-rentabilidad/{punto_id}")
def reporte_rentabilidad(punto_id: int):
    """Análisis de rentabilidad del día actual"""
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

        # Agrupar por tipo de venta
        por_tipo: dict = {}
        for t in transacciones:
            tipo = t.tipo_venta.value if hasattr(t.tipo_venta, 'value') else str(t.tipo_venta)
            if tipo not in por_tipo:
                por_tipo[tipo] = {"tipo_venta": tipo, "cantidad": 0, "total_venta": 0, "margen_total": 0}
            por_tipo[tipo]["cantidad"] += 1
            por_tipo[tipo]["total_venta"] += t.precio_venta
            por_tipo[tipo]["margen_total"] += t.margen_bruto

        # Agrupar por método de pago
        por_metodo: dict = {"efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0}
        for t in transacciones:
            if t.metodo_pago in por_metodo:
                por_metodo[t.metodo_pago] += t.precio_venta

        # Top productos por cantidad
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
            "top_productos": [{"producto": p, "cantidad": c} for p, c in producto_counter.most_common(10)],
            "tiene_costos": tiene_costos,
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
