"""APIs de órdenes - sin autenticación"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from foodops.domain.schemas import OrdenCreate
from foodops.db.models import Orden, OrdenItem, OrdenEstado, MetodoPago
from foodops.core.config import settings

router = APIRouter(prefix="/api/ordenes", tags=["ordenes"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

@router.post("/")
def crear_orden(orden: OrdenCreate):
    """Crear nueva orden"""
    session = Session()
    try:
        numero_orden = f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        total = sum((item.cantidad * item.precio_unitario) for item in orden.items) if orden.items else 100.0
        
        nueva_orden = Orden(
            punto_id=2,
            numero_orden=numero_orden,
            cliente_nombre=orden.cliente_nombre,
            cliente_telefono=orden.cliente_telefono,
            metodo_pago=MetodoPago(orden.metodo_pago),
            total=total,
            es_domicilio=orden.es_domicilio,
            estado=OrdenEstado.PENDIENTE
        )
        
        session.add(nueva_orden)
        session.flush()
        
        if orden.items:
            for item in orden.items:
                orden_item = OrdenItem(
                    orden_id=nueva_orden.id,
                    producto=item.producto,
                    cantidad=item.cantidad,
                    precio_unitario=item.precio_unitario,
                    subtotal=item.cantidad * item.precio_unitario,
                    especiales=item.especiales
                )
                session.add(orden_item)
        
        session.commit()
        
        return {
            "id": nueva_orden.id,
            "numero_orden": nueva_orden.numero_orden,
            "estado": nueva_orden.estado.value,
            "cliente_nombre": nueva_orden.cliente_nombre,
            "total": float(nueva_orden.total),
            "es_domicilio": nueva_orden.es_domicilio,
            "created_at": str(nueva_orden.created_at)
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()

@router.get("/{punto_id}")
def listar_ordenes(punto_id: int):
    """Listar órdenes por punto de venta"""
    session = Session()
    try:
        ordenes = session.execute(select(Orden).where(Orden.punto_id == punto_id)).scalars().all()
        return [{"id": o.id, "numero_orden": o.numero_orden, "estado": o.estado.value, "total": float(o.total), "cliente_nombre": o.cliente_nombre, "es_domicilio": o.es_domicilio, "created_at": str(o.created_at)} for o in ordenes]
    finally:
        session.close()
