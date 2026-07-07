"""Dashboard de gerencia: stock en vivo + recomendaciones + pedidos pendientes por tienda"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from foodops.api.router_stock import _pedido_dict, _recomendaciones, _stock_actual
from foodops.core.auth import TokenData, requiere_rol
from foodops.core.config import settings
from foodops.db.models import PuntoVenta
from foodops.db.models_stock import PedidoReabastecimiento

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gerencia", tags=["gerencia"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_GERENCIA = ("gerente_general", "admin")


def _dashboard_punto(session, punto: PuntoVenta) -> dict:
    stock = _stock_actual(session, punto.id, date.today())
    recomendaciones = _recomendaciones(session, punto.id)
    pedidos_pendientes = session.execute(
        select(PedidoReabastecimiento).where(
            PedidoReabastecimiento.punto_id == punto.id,
            PedidoReabastecimiento.estado.in_(("pendiente", "confirmado")),
        )
    ).scalars().all()

    items_urgentes = sum(1 for r in recomendaciones if r["recomendacion"] == "URGENTE")
    items_ok = sum(1 for r in recomendaciones if r["recomendacion"] == "OK")
    stock_total_valor = sum(s["stock_estimado"] for s in stock)

    return {
        "punto": {"id": punto.id, "nombre": punto.nombre, "direccion": punto.direccion},
        "stock": stock,
        "recomendaciones": recomendaciones,
        "pedidos_pendientes": [_pedido_dict(session, p) for p in pedidos_pendientes],
        "resumen": {
            "items_urgentes": items_urgentes,
            "items_ok": items_ok,
            "stock_total_valor": round(stock_total_valor, 2),
        },
    }


@router.get("/dashboard")
def dashboard_gerente(
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        effective_punto_id = punto_id or current_user.punto_id
        punto = session.get(PuntoVenta, effective_punto_id)
        if not punto:
            raise HTTPException(status_code=404, detail="Punto de venta no encontrado")
        return _dashboard_punto(session, punto)
    except HTTPException:
        raise
    finally:
        session.close()


@router.get("/dashboard/multi-tienda")
def dashboard_multi_tienda(current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA))):
    session = Session()
    try:
        puntos = session.execute(select(PuntoVenta).where(PuntoVenta.activo.is_(True))).scalars().all()
        resultado = []
        for punto in puntos:
            data = _dashboard_punto(session, punto)
            data["recomendaciones"] = sorted(
                (r for r in data["recomendaciones"] if r["recomendacion"] == "URGENTE"),
                key=lambda r: r["dias_disponibles"] or 0,
            )[:5]
            resultado.append(data)
        return resultado
    finally:
        session.close()
