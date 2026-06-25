"""APIs de órdenes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime

from foodops.domain.schemas import OrdenCreate
from foodops.db.models import Orden, OrdenItem, OrdenEstado, MetodoPago
from foodops.db.database import get_db
from foodops.core.auth import get_current_user, TokenData

router = APIRouter(prefix="/api/ordenes", tags=["ordenes"])

@router.post("/", response_model=dict)
async def crear_orden(
    orden: OrdenCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Crea una nueva orden"""
    
    if not current_user.punto_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario no está asignado a ningún punto"
        )
    
    numero_orden = f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    total = sum(item.cantidad * item.precio_unitario for item in orden.items)
    
    nueva_orden = Orden(
        punto_id=current_user.punto_id,
        numero_orden=numero_orden,
        cliente_nombre=orden.cliente_nombre,
        cliente_telefono=orden.cliente_telefono,
        metodo_pago=MetodoPago(orden.metodo_pago),
        total=total,
        es_domicilio=orden.es_domicilio,
        estado=OrdenEstado.PENDIENTE
    )
    
    db.add(nueva_orden)
    await db.flush()
    
    for item in orden.items:
        subtotal = item.cantidad * item.precio_unitario
        orden_item = OrdenItem(
            orden_id=nueva_orden.id,
            producto=item.producto,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=subtotal,
            especiales=item.especiales
        )
        db.add(orden_item)
    
    await db.commit()
    await db.refresh(nueva_orden)
    
    return {
        "id": nueva_orden.id,
        "numero_orden": nueva_orden.numero_orden,
        "estado": nueva_orden.estado.value,
        "total": nueva_orden.total,
        "created_at": nueva_orden.created_at
    }

@router.get("/{punto_id}")
async def listar_ordenes(
    punto_id: int,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lista órdenes del punto"""
    
    stmt = select(Orden).where(Orden.punto_id == punto_id)
    result = await db.execute(stmt)
    ordenes = result.scalars().all()
    
    return [
        {
            "id": o.id,
            "numero_orden": o.numero_orden,
            "estado": o.estado.value,
            "total": o.total,
            "created_at": o.created_at
        }
        for o in ordenes
    ]
