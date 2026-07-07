"""APIs de stock en vivo y reabastecimiento (Etapa 2.5)"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import TokenData, get_current_user, requiere_rol
from foodops.core.config import settings
from foodops.db.models import TransaccionVenta
from foodops.db.models_caja import InventarioDetalle, InventarioDiario, ItemInventario
from foodops.db.models_stock import (
    PedidoReabastecimiento,
    PedidoReabastecimientoItem,
    ProductoComponente,
    ProductoMenu,
    TransaccionComponente,
)
from foodops.domain.schemas_stock import PedidoReabastecimientoCreate, RecibirPedidoRequest
from foodops.utils.timeutils import local_day_bounds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stock"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_TIENDA = ("resp_tienda", "gerente_general", "admin")
_ROLES_GERENCIA = ("gerente_general", "admin")
_DIAS_PROMEDIO = 7


def _day_bounds(fecha: date):
    return local_day_bounds(fecha)


def _resolve_punto_id(current_user: TokenData, punto_id: Optional[int]) -> int:
    if punto_id is not None and current_user.rol not in _ROLES_GERENCIA:
        punto_id = None
    return punto_id if punto_id is not None else current_user.punto_id


def _detalle_map(session, punto_id: int, fecha: date, momento: str) -> dict:
    rows = session.execute(
        select(InventarioDetalle)
        .join(InventarioDiario, InventarioDiario.id == InventarioDetalle.inventario_id)
        .where(
            InventarioDiario.punto_id == punto_id,
            InventarioDiario.fecha == fecha,
            InventarioDiario.momento == momento,
        )
    ).scalars().all()
    return {d.item_id: Decimal(str(d.cantidad)) for d in rows}


def _consumo_teorico_exacto(session, punto_id: int, fecha: date) -> dict:
    """SUM(transaccion_componentes.cantidad) del día, exacto por receta (no estimado)."""
    day_start, day_end = _day_bounds(fecha)
    rows = session.execute(
        select(TransaccionComponente.item_inventario_id, func.sum(TransaccionComponente.cantidad))
        .join(TransaccionVenta, TransaccionVenta.id == TransaccionComponente.transaccion_id)
        .where(
            TransaccionVenta.punto_id == punto_id,
            TransaccionComponente.created_at >= day_start,
            TransaccionComponente.created_at < day_end,
        )
        .group_by(TransaccionComponente.item_inventario_id)
    ).all()
    return {item_id: Decimal(str(total)) for item_id, total in rows}


def _recibido_hoy(session, punto_id: int, fecha: date) -> dict:
    day_start, day_end = _day_bounds(fecha)
    rows = session.execute(
        select(PedidoReabastecimientoItem.item_inventario_id, func.sum(PedidoReabastecimientoItem.cantidad_recibida))
        .join(PedidoReabastecimiento, PedidoReabastecimiento.id == PedidoReabastecimientoItem.pedido_id)
        .where(
            PedidoReabastecimiento.punto_id == punto_id,
            PedidoReabastecimiento.estado == "entregado",
            PedidoReabastecimientoItem.cantidad_recibida.isnot(None),
            PedidoReabastecimiento.confirmado_at >= day_start,
            PedidoReabastecimiento.confirmado_at < day_end,
        )
        .group_by(PedidoReabastecimientoItem.item_inventario_id)
    ).all()
    return {item_id: Decimal(str(total)) for item_id, total in rows if total is not None}


def _stock_actual(session, punto_id: int, fecha: date) -> list:
    items = session.execute(
        select(ItemInventario).where(ItemInventario.activo.is_(True)).order_by(ItemInventario.orden_conteo)
    ).scalars().all()

    apertura_map = _detalle_map(session, punto_id, fecha, "apertura")
    cierre_map = _detalle_map(session, punto_id, fecha, "cierre")
    consumo_map = _consumo_teorico_exacto(session, punto_id, fecha)
    recibido_map = _recibido_hoy(session, punto_id, fecha)

    resultado = []
    for item in items:
        apertura = apertura_map.get(item.id, Decimal("0"))
        consumo_teorico = consumo_map.get(item.id, Decimal("0"))
        recibido = recibido_map.get(item.id, Decimal("0"))
        stock_estimado = apertura + recibido - consumo_teorico

        cierre = cierre_map.get(item.id)
        fuga_detectada = None
        if cierre is not None:
            fuga_detectada = apertura - cierre - consumo_teorico

        resultado.append(
            {
                "item_id": item.id,
                "nombre": item.nombre,
                "unidad": item.unidad,
                "cantidad_apertura": float(apertura),
                "consumo_teorico": float(consumo_teorico),
                "stock_estimado": float(stock_estimado),
                "cantidad_cierre": float(cierre) if cierre is not None else None,
                "fuga_detectada": float(fuga_detectada) if fuga_detectada is not None else None,
            }
        )
    return resultado


def _consumo_promedio_diario(session, punto_id: int) -> dict:
    """Promedio de consumo teórico exacto de los últimos _DIAS_PROMEDIO días (total/dias)."""
    hoy = date.today()
    inicio, _ = _day_bounds(hoy - timedelta(days=_DIAS_PROMEDIO))
    _, fin = _day_bounds(hoy - timedelta(days=1))

    rows = session.execute(
        select(TransaccionComponente.item_inventario_id, func.sum(TransaccionComponente.cantidad))
        .join(TransaccionVenta, TransaccionVenta.id == TransaccionComponente.transaccion_id)
        .where(
            TransaccionVenta.punto_id == punto_id,
            TransaccionComponente.created_at >= inicio,
            TransaccionComponente.created_at < fin,
        )
        .group_by(TransaccionComponente.item_inventario_id)
    ).all()
    return {item_id: Decimal(str(total)) / _DIAS_PROMEDIO for item_id, total in rows}


@router.get("/stock/actual")
def stock_actual(
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    effective_punto_id = _resolve_punto_id(current_user, punto_id)
    session = Session()
    try:
        return _stock_actual(session, effective_punto_id, date.today())
    finally:
        session.close()


@router.get("/stock/proyeccion")
def stock_proyeccion(
    punto_id: Optional[int] = Query(default=None),
    dias: int = Query(default=3, ge=1, le=30),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    effective_punto_id = _resolve_punto_id(current_user, punto_id)
    session = Session()
    try:
        stock_hoy = {s["item_id"]: s for s in _stock_actual(session, effective_punto_id, date.today())}
        promedio_map = _consumo_promedio_diario(session, effective_punto_id)

        resultado = []
        for item_id, s in stock_hoy.items():
            promedio = promedio_map.get(item_id, Decimal("0"))
            stock_proyectado = Decimal(str(s["stock_estimado"])) - promedio * dias
            resultado.append(
                {
                    "item_id": item_id,
                    "nombre": s["nombre"],
                    "consumo_promedio_diario": float(promedio),
                    "stock_proyectado": float(stock_proyectado),
                }
            )
        return resultado
    finally:
        session.close()


def _recomendaciones(session, punto_id: int) -> list:
    stock_hoy = _stock_actual(session, punto_id, date.today())
    promedio_map = _consumo_promedio_diario(session, punto_id)

    resultado = []
    for s in stock_hoy:
        stock_actual_val = Decimal(str(s["stock_estimado"]))
        promedio = promedio_map.get(s["item_id"], Decimal("0"))

        if promedio == 0:
            dias_disponibles = None
            recomendacion = "OK"
            cantidad_sugerida = Decimal("0")
        else:
            dias_disponibles = stock_actual_val / promedio
            if dias_disponibles < 2:
                recomendacion = "URGENTE"
                cantidad_sugerida = promedio * 5
            elif dias_disponibles < 5:
                recomendacion = "NORMAL"
                cantidad_sugerida = promedio * 7
            else:
                recomendacion = "OK"
                cantidad_sugerida = Decimal("0")

        resultado.append(
            {
                "item_id": s["item_id"],
                "nombre": s["nombre"],
                "stock_actual": float(stock_actual_val),
                "consumo_diario_promedio": float(promedio),
                "dias_disponibles": float(dias_disponibles) if dias_disponibles is not None else None,
                "recomendacion": recomendacion,
                "cantidad_sugerida": float(cantidad_sugerida),
            }
        )
    return resultado


@router.get("/stock/recomendaciones")
def stock_recomendaciones(
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    effective_punto_id = _resolve_punto_id(current_user, punto_id)
    session = Session()
    try:
        return _recomendaciones(session, effective_punto_id)
    finally:
        session.close()


def _pedido_dict(session, pedido: PedidoReabastecimiento) -> dict:
    items = session.execute(
        select(PedidoReabastecimientoItem, ItemInventario)
        .join(ItemInventario, ItemInventario.id == PedidoReabastecimientoItem.item_inventario_id)
        .where(PedidoReabastecimientoItem.pedido_id == pedido.id)
    ).all()
    return {
        "id": pedido.id,
        "punto_id": pedido.punto_id,
        "tipo": pedido.tipo,
        "estado": pedido.estado,
        "total_estimado": float(pedido.total_estimado) if pedido.total_estimado is not None else None,
        "creado_por": pedido.creado_por,
        "confirmado_por": pedido.confirmado_por,
        "created_at": str(pedido.created_at),
        "confirmado_at": str(pedido.confirmado_at) if pedido.confirmado_at else None,
        "items": [
            {
                "id": pi.id,
                "item_inventario_id": pi.item_inventario_id,
                "nombre": it.nombre,
                "cantidad_solicitada": float(pi.cantidad_solicitada),
                "cantidad_recibida": float(pi.cantidad_recibida) if pi.cantidad_recibida is not None else None,
                "precio_unitario": float(pi.precio_unitario) if pi.precio_unitario is not None else None,
                "costo_total": float(pi.costo_total) if pi.costo_total is not None else None,
                "razon_solicitud": pi.razon_solicitud,
            }
            for pi, it in items
        ],
    }


@router.post("/pedidos-reabastecimiento")
def crear_pedido_reabastecimiento(
    body: PedidoReabastecimientoCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        pedido = PedidoReabastecimiento(
            punto_id=current_user.punto_id,
            tipo=body.tipo.value,
            estado="pendiente",
            creado_por=current_user.user_id,
        )
        session.add(pedido)
        session.flush()

        for entry in body.items:
            session.add(
                PedidoReabastecimientoItem(
                    pedido_id=pedido.id,
                    item_inventario_id=entry.item_id,
                    cantidad_solicitada=entry.cantidad,
                    razon_solicitud=entry.razon.value if entry.razon else None,
                )
            )

        registrar_auditoria(
            session,
            accion="CREAR_PEDIDO_REABASTECIMIENTO",
            entidad="pedido_reabastecimiento",
            entidad_id=pedido.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"tipo": body.tipo.value, "items": len(body.items)},
        )
        session.commit()
        return _pedido_dict(session, pedido)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/pedidos-reabastecimiento")
def listar_pedidos_reabastecimiento(
    estado: Optional[str] = Query(default=None),
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    effective_punto_id = _resolve_punto_id(current_user, punto_id)
    session = Session()
    try:
        stmt = select(PedidoReabastecimiento).where(PedidoReabastecimiento.punto_id == effective_punto_id)
        if estado:
            stmt = stmt.where(PedidoReabastecimiento.estado == estado)
        pedidos = session.execute(stmt.order_by(PedidoReabastecimiento.created_at.desc())).scalars().all()
        return [_pedido_dict(session, p) for p in pedidos]
    finally:
        session.close()


@router.post("/pedidos-reabastecimiento/{pedido_id}/confirmar")
def confirmar_pedido_reabastecimiento(
    pedido_id: int,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        pedido = session.get(PedidoReabastecimiento, pedido_id)
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        if pedido.estado != "pendiente":
            raise HTTPException(status_code=400, detail="Solo se puede confirmar un pedido pendiente")

        pedido.estado = "confirmado"
        pedido.confirmado_por = current_user.user_id

        registrar_auditoria(
            session,
            accion="CONFIRMAR_PEDIDO_REABASTECIMIENTO",
            entidad="pedido_reabastecimiento",
            entidad_id=pedido.id,
            usuario_id=current_user.user_id,
            punto_id=pedido.punto_id,
        )
        session.commit()
        return _pedido_dict(session, pedido)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.post("/pedidos-reabastecimiento/{pedido_id}/recibir")
def recibir_pedido_reabastecimiento(
    pedido_id: int,
    body: RecibirPedidoRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        pedido = session.get(PedidoReabastecimiento, pedido_id)
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        if pedido.estado not in ("confirmado", "pendiente"):
            raise HTTPException(status_code=400, detail="Este pedido ya fue recibido o fue cancelado")

        items_por_id = {
            pi.item_inventario_id: pi
            for pi in session.execute(
                select(PedidoReabastecimientoItem).where(PedidoReabastecimientoItem.pedido_id == pedido.id)
            ).scalars().all()
        }
        diferencias = []
        for entry in body.items_recibidos:
            pi = items_por_id.get(entry.item_id)
            if not pi:
                continue
            pi.cantidad_recibida = entry.cantidad
            if float(pi.cantidad_solicitada) != entry.cantidad:
                diferencias.append(
                    {"item_id": entry.item_id, "solicitado": float(pi.cantidad_solicitada), "recibido": entry.cantidad}
                )

        pedido.estado = "entregado"
        # confirmado_at se usa también como "recibido_at" (no existe columna separada):
        # se sobreescribe aquí para que _recibido_hoy() atribuya el stock al día real de recepción.
        pedido.confirmado_at = datetime.utcnow()

        registrar_auditoria(
            session,
            accion="RECIBIR_PEDIDO_REABASTECIMIENTO",
            entidad="pedido_reabastecimiento",
            entidad_id=pedido.id,
            usuario_id=current_user.user_id,
            punto_id=pedido.punto_id,
            detalle={"diferencias": diferencias} if diferencias else None,
        )
        session.commit()
        return _pedido_dict(session, pedido)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/productos-menu")
def listar_productos_menu(current_user: TokenData = Depends(get_current_user)):
    """Catálogo de productos con su receta (producto_componentes), para que el POS
    pueda previsualizar qué componentes de inventario se consumirán al vender.
    Abierto a cualquier rol autenticado (lo usa la pantalla de nueva orden)."""
    session = Session()
    try:
        productos = session.execute(
            select(ProductoMenu).where(ProductoMenu.activo.is_(True))
        ).scalars().all()
        componentes = session.execute(
            select(ProductoComponente, ItemInventario)
            .join(ItemInventario, ItemInventario.id == ProductoComponente.item_inventario_id)
        ).all()
        por_producto: dict = {}
        for c, item in componentes:
            por_producto.setdefault(c.producto_menu_id, []).append(
                {
                    "item_id": item.id,
                    "nombre": item.nombre,
                    "unidad": item.unidad,
                    "tipo": item.tipo,
                    "cantidad": float(c.cantidad),
                    "elegible": c.elegible,
                    "grupo_elegible": c.grupo_elegible,
                    "nombre_grupo": c.nombre_grupo,
                }
            )
        return [
            {
                "id": p.id,
                "nombre": p.nombre,
                "tipo": p.tipo,
                "componentes": por_producto.get(p.id, []),
            }
            for p in productos
        ]
    finally:
        session.close()
