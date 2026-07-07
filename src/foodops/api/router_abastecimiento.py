"""Módulo D: abastecimiento inteligente - sugerencias por responsable
(POLLO/VEGETAL/DESECHABLE_SALSA), generación de pedidos multi-tienda y reglas
min/máx. Reutiliza PedidoReabastecimiento/PedidoReabastecimientoItem (ver
migración 007_modulo_d_abastecimiento) en vez de un modelo de pedidos paralelo:
la recepción sigue pasando por POST /api/pedidos-reabastecimiento/{id}/recibir
(router_stock.py), ya construida y probada."""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import TokenData, requiere_rol
from foodops.core.config import settings
from foodops.db.models import PuntoVenta
from foodops.db.models_caja import ItemInventario
from foodops.db.models_stock import (
    PedidoReabastecimiento,
    PedidoReabastecimientoItem,
    ReglaReabastecimiento,
)
from foodops.domain.schemas_stock import (
    PedidoAbastecimientoCrearRequest,
    ReglaReabastecimientoCreate,
    ReglaReabastecimientoUpdate,
    ResponsableAbastecimiento,
)
from foodops.api.router_stock import _consumo_teorico_exacto, _stock_actual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["abastecimiento"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_CENTRAL = ("gerente_central", "gerente_general", "admin")
_ROLES_GERENCIA = ("gerente_general", "admin")
_URGENCIA_ORDEN = {"URGENTE": 0, "NORMAL": 1, "OK": 2}


def _factor_dia_semana(fecha: date, regla: ReglaReabastecimiento) -> float:
    dia = fecha.weekday()  # lunes=0 ... sábado=5, domingo=6
    if dia == 6:
        return float(regla.factor_domingo)
    if dia == 5:
        return float(regla.factor_sabado)
    return 1.0


def _regla_para(session, item_id: int, punto_id: int) -> Optional[ReglaReabastecimiento]:
    reglas = session.execute(
        select(ReglaReabastecimiento).where(
            ReglaReabastecimiento.item_inventario_id == item_id,
            ReglaReabastecimiento.activo.is_(True),
            (ReglaReabastecimiento.punto_venta_id == punto_id) | (ReglaReabastecimiento.punto_venta_id.is_(None)),
        )
    ).scalars().all()
    especifica = next((r for r in reglas if r.punto_venta_id == punto_id), None)
    return especifica or next((r for r in reglas if r.punto_venta_id is None), None)


# ---------------------------------------------------------------------------
# Sugerencias
# ---------------------------------------------------------------------------


@router.get("/abastecimiento/sugerencias")
def sugerencias_abastecimiento(
    responsable_tipo: ResponsableAbastecimiento = Query(...),
    fecha: Optional[date] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CENTRAL)),
):
    fecha_objetivo = fecha or date.today()
    ayer = fecha_objetivo - timedelta(days=1)

    session = Session()
    try:
        items = session.execute(
            select(ItemInventario).where(
                ItemInventario.responsable_abastecimiento == responsable_tipo.value,
                ItemInventario.activo.is_(True),
            )
        ).scalars().all()
        if not items:
            return {"fecha": str(fecha_objetivo), "factor_dia": 1.0, "puntos": []}

        puntos = session.execute(select(PuntoVenta).where(PuntoVenta.activo.is_(True))).scalars().all()

        factor_dia_referencia = 1.0
        resultado_puntos = []
        for punto in puntos:
            consumo_ayer_map = _consumo_teorico_exacto(session, punto.id, ayer)
            stock_map = {s["item_id"]: s["stock_estimado"] for s in _stock_actual(session, punto.id, fecha_objetivo)}

            items_sugeridos = []
            for item in items:
                consumo_ayer = float(consumo_ayer_map.get(item.id, Decimal("0")))
                if consumo_ayer == 0:
                    continue  # sin historial de venta ayer: no hay base para sugerir

                regla = _regla_para(session, item.id, punto.id)
                if not regla:
                    continue

                factor = _factor_dia_semana(fecha_objetivo, regla)
                factor_dia_referencia = factor
                stock_actual_val = float(stock_map.get(item.id, 0))
                consumo_esperado = consumo_ayer * factor
                minimo = float(regla.stock_minimo)
                maximo = float(regla.stock_maximo)

                cantidad_sugerida = max(0.0, minimo - stock_actual_val + consumo_esperado * 0.5)
                tope_maximo = max(0.0, maximo - stock_actual_val)
                cantidad_sugerida = min(cantidad_sugerida, tope_maximo)

                if stock_actual_val < minimo * 0.5:
                    urgencia = "URGENTE"
                elif stock_actual_val < minimo:
                    urgencia = "NORMAL"
                else:
                    urgencia = "OK"

                items_sugeridos.append(
                    {
                        "item_id": item.id,
                        "item_nombre": item.nombre,
                        "stock_actual": round(stock_actual_val, 2),
                        "consumo_ayer": round(consumo_ayer, 2),
                        "cantidad_sugerida": round(cantidad_sugerida, 2),
                        "urgencia": urgencia,
                    }
                )

            if items_sugeridos:
                items_sugeridos.sort(key=lambda x: _URGENCIA_ORDEN[x["urgencia"]])
                resultado_puntos.append(
                    {"punto_id": punto.id, "punto_nombre": punto.nombre, "items": items_sugeridos}
                )

        return {"fecha": str(fecha_objetivo), "factor_dia": factor_dia_referencia, "puntos": resultado_puntos}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Pedidos de abastecimiento (reutiliza pedidos_reabastecimiento)
# ---------------------------------------------------------------------------


def _pedido_abastecimiento_dict(session, pedido: PedidoReabastecimiento) -> dict:
    items = session.execute(
        select(PedidoReabastecimientoItem, ItemInventario)
        .join(ItemInventario, ItemInventario.id == PedidoReabastecimientoItem.item_inventario_id)
        .where(PedidoReabastecimientoItem.pedido_id == pedido.id)
    ).all()
    punto = session.get(PuntoVenta, pedido.punto_id)
    # No hay un estado 'enviado' propio en la tabla: se deriva de
    # estado=confirmado + fecha_envio ya asignado, para no bifurcar el enum
    # de estados que ya usa el flujo clásico de tienda (pendiente/confirmado/entregado).
    estado_visible = pedido.estado
    if pedido.estado == "confirmado" and pedido.fecha_envio is not None:
        estado_visible = "enviado"
    return {
        "id": pedido.id,
        "punto_id": pedido.punto_id,
        "punto_nombre": punto.nombre if punto else None,
        "responsable_tipo": pedido.responsable_tipo,
        "estado": estado_visible,
        "fecha_envio": str(pedido.fecha_envio) if pedido.fecha_envio else None,
        "created_at": str(pedido.created_at),
        "items": [
            {
                "item_id": pi.item_inventario_id,
                "item_nombre": it.nombre,
                "cantidad_solicitada": float(pi.cantidad_solicitada),
                "cantidad_recibida": float(pi.cantidad_recibida) if pi.cantidad_recibida is not None else None,
            }
            for pi, it in items
        ],
    }


@router.post("/abastecimiento/pedido/crear", status_code=201)
def crear_pedido_abastecimiento(
    body: PedidoAbastecimientoCrearRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CENTRAL)),
):
    session = Session()
    try:
        por_punto: dict = {}
        for entry in body.items:
            por_punto.setdefault(entry.punto_venta_id, []).append(entry)

        puntos_validos = set(
            session.execute(
                select(PuntoVenta.id).where(PuntoVenta.id.in_(por_punto.keys()))
            ).scalars().all()
        )
        faltantes = set(por_punto.keys()) - puntos_validos
        if faltantes:
            raise HTTPException(status_code=400, detail=f"punto_venta_id inválido(s): {sorted(faltantes)}")

        pedidos_creados = []
        for punto_id, entries in por_punto.items():
            pedido = PedidoReabastecimiento(
                punto_id=punto_id,
                tipo="solicitud_central",
                estado="confirmado",
                responsable_tipo=body.responsable_tipo.value,
                creado_por=current_user.user_id,
                confirmado_por=current_user.user_id,
                confirmado_at=datetime.utcnow(),
            )
            session.add(pedido)
            session.flush()

            for entry in entries:
                session.add(
                    PedidoReabastecimientoItem(
                        pedido_id=pedido.id,
                        item_inventario_id=entry.item_id,
                        cantidad_solicitada=entry.cantidad_final,
                    )
                )

            registrar_auditoria(
                session,
                accion="CREAR_PEDIDO_ABASTECIMIENTO",
                entidad="pedido_reabastecimiento",
                entidad_id=pedido.id,
                usuario_id=current_user.user_id,
                punto_id=punto_id,
                detalle={"responsable_tipo": body.responsable_tipo.value, "items": len(entries)},
            )
            pedidos_creados.append(pedido.id)

        session.commit()
        return {"pedido_ids": pedidos_creados, "estado": "confirmado"}
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.post("/abastecimiento/pedido/{pedido_id}/enviar")
def enviar_pedido_abastecimiento(
    pedido_id: int,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CENTRAL)),
):
    session = Session()
    try:
        pedido = session.get(PedidoReabastecimiento, pedido_id)
        if not pedido or pedido.responsable_tipo is None:
            raise HTTPException(status_code=404, detail="Pedido de abastecimiento no encontrado")
        if pedido.estado != "confirmado":
            raise HTTPException(status_code=400, detail="Solo se puede enviar un pedido confirmado")
        if pedido.fecha_envio is not None:
            raise HTTPException(status_code=400, detail="Este pedido ya fue marcado como enviado")

        pedido.fecha_envio = date.today()

        registrar_auditoria(
            session,
            accion="ENVIAR_PEDIDO_ABASTECIMIENTO",
            entidad="pedido_reabastecimiento",
            entidad_id=pedido.id,
            usuario_id=current_user.user_id,
            punto_id=pedido.punto_id,
        )
        session.commit()
        return _pedido_abastecimiento_dict(session, pedido)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/abastecimiento/pedidos")
def listar_pedidos_abastecimiento(
    responsable_tipo: Optional[ResponsableAbastecimiento] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CENTRAL)),
):
    session = Session()
    try:
        stmt = select(PedidoReabastecimiento).where(PedidoReabastecimiento.responsable_tipo.isnot(None))
        if responsable_tipo:
            stmt = stmt.where(PedidoReabastecimiento.responsable_tipo == responsable_tipo.value)
        pedidos = session.execute(stmt.order_by(PedidoReabastecimiento.created_at.desc())).scalars().all()
        dicts = [_pedido_abastecimiento_dict(session, p) for p in pedidos]
        if estado:
            dicts = [d for d in dicts if d["estado"] == estado]
        return {"pedidos": dicts}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Reglas de reabastecimiento (min/máx + factores)
# ---------------------------------------------------------------------------


def _regla_dict(session, regla: ReglaReabastecimiento) -> dict:
    item = session.get(ItemInventario, regla.item_inventario_id)
    return {
        "id": regla.id,
        "item_inventario_id": regla.item_inventario_id,
        "item_nombre": item.nombre if item else "",
        "punto_venta_id": regla.punto_venta_id,
        "stock_minimo": float(regla.stock_minimo),
        "stock_maximo": float(regla.stock_maximo),
        "consumo_diario_base": float(regla.consumo_diario_base) if regla.consumo_diario_base is not None else None,
        "factor_sabado": float(regla.factor_sabado),
        "factor_domingo": float(regla.factor_domingo),
        "cantidad_fija_diaria": float(regla.cantidad_fija_diaria) if regla.cantidad_fija_diaria is not None else None,
        "activo": regla.activo,
    }


@router.get("/reglas-reabastecimiento")
def listar_reglas_reabastecimiento(
    item_id: Optional[int] = Query(default=None),
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_CENTRAL)),
):
    session = Session()
    try:
        stmt = select(ReglaReabastecimiento)
        if item_id is not None:
            stmt = stmt.where(ReglaReabastecimiento.item_inventario_id == item_id)
        if punto_id is not None:
            stmt = stmt.where(ReglaReabastecimiento.punto_venta_id == punto_id)
        reglas = session.execute(stmt.order_by(ReglaReabastecimiento.item_inventario_id)).scalars().all()
        return {"reglas": [_regla_dict(session, r) for r in reglas]}
    finally:
        session.close()


@router.post("/reglas-reabastecimiento", status_code=201)
def crear_regla_reabastecimiento(
    body: ReglaReabastecimientoCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        item = session.get(ItemInventario, body.item_inventario_id)
        if not item:
            raise HTTPException(status_code=400, detail="item_inventario_id inválido")

        existente = session.execute(
            select(ReglaReabastecimiento).where(
                ReglaReabastecimiento.item_inventario_id == body.item_inventario_id,
                ReglaReabastecimiento.punto_venta_id == body.punto_venta_id,
            )
        ).scalars().first()
        if existente:
            raise HTTPException(status_code=400, detail="Ya existe una regla para este item y punto de venta")

        regla = ReglaReabastecimiento(**body.model_dump())
        session.add(regla)
        session.flush()

        registrar_auditoria(
            session,
            accion="CREAR_REGLA_REABASTECIMIENTO",
            entidad="regla_reabastecimiento",
            entidad_id=regla.id,
            usuario_id=current_user.user_id,
            detalle={"item_inventario_id": regla.item_inventario_id, "punto_venta_id": regla.punto_venta_id},
        )
        session.commit()
        return _regla_dict(session, regla)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.patch("/reglas-reabastecimiento/{regla_id}")
def actualizar_regla_reabastecimiento(
    regla_id: int,
    body: ReglaReabastecimientoUpdate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        regla = session.get(ReglaReabastecimiento, regla_id)
        if not regla:
            raise HTTPException(status_code=404, detail="Regla no encontrada")

        cambios = body.model_dump(exclude_unset=True)
        nuevo_min = cambios.get("stock_minimo", regla.stock_minimo)
        nuevo_max = cambios.get("stock_maximo", regla.stock_maximo)
        if Decimal(str(nuevo_max)) < Decimal(str(nuevo_min)):
            raise HTTPException(status_code=400, detail="stock_maximo no puede ser menor que stock_minimo")

        for campo, valor in cambios.items():
            setattr(regla, campo, valor)
        regla.updated_at = datetime.utcnow()

        detalle_auditoria = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in cambios.items()}
        registrar_auditoria(
            session,
            accion="ACTUALIZAR_REGLA_REABASTECIMIENTO",
            entidad="regla_reabastecimiento",
            entidad_id=regla.id,
            usuario_id=current_user.user_id,
            detalle=detalle_auditoria,
        )
        session.commit()
        return _regla_dict(session, regla)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()
