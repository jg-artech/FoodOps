"""APIs de Caja y Tienda (Módulo D): efectivo, inventario diario, gastos, desperdicios, fondos de repartidor"""
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
from foodops.db.models_caja import (
    CajaDiaria,
    Desperdicio,
    FondoRepartidor,
    Gasto,
    InventarioDetalle,
    InventarioDiario,
    ItemInventario,
    TransaccionPedido,
)
from foodops.domain.schemas_caja import (
    CajaDiariaCerrarRequest,
    CajaDiariaCreate,
    DesperdicioCreate,
    FondoRepartidorCreate,
    FondoRepartidorLiquidarRequest,
    GastoCreate,
    InventarioDiarioSubmit,
    ItemInventarioCreate,
    ItemInventarioUpdate,
    TransaccionPedidoCreate,
)
from foodops.utils.timeutils import local_day_bounds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["caja"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_TIENDA = ("resp_tienda", "gerente_general", "admin")
_ROLES_GERENCIA = ("gerente_general", "admin")
_UMBRAL_DESCUADRE = Decimal("10.00")


def _day_bounds(fecha: date) -> tuple[datetime, datetime]:
    return local_day_bounds(fecha)


def _get_caja_abierta(session, punto_id: int) -> CajaDiaria:
    caja = session.execute(
        select(CajaDiaria).where(
            CajaDiaria.punto_id == punto_id,
            CajaDiaria.estado == "abierta",
        )
    ).scalars().first()
    if not caja:
        raise HTTPException(status_code=400, detail="No hay caja abierta para este punto de venta")
    return caja


def _resolve_punto_id(current_user: TokenData, punto_id: Optional[int]) -> int:
    if punto_id is not None and current_user.rol not in _ROLES_GERENCIA:
        punto_id = None
    return punto_id if punto_id is not None else current_user.punto_id


def _caja_dict(caja: CajaDiaria) -> dict:
    return {
        "id": caja.id,
        "punto_id": caja.punto_id,
        "fecha": str(caja.fecha),
        "fondo_inicial": float(caja.fondo_inicial),
        "efectivo_esperado": float(caja.efectivo_esperado) if caja.efectivo_esperado is not None else None,
        "efectivo_contado": float(caja.efectivo_contado) if caja.efectivo_contado is not None else None,
        "descuadre": float(caja.descuadre) if caja.descuadre is not None else None,
        "estado": caja.estado,
        "abierta_por": caja.abierta_por,
        "cerrada_por": caja.cerrada_por,
        "observacion_gerente": caja.observacion_gerente,
        "created_at": str(caja.created_at),
        "cerrada_at": str(caja.cerrada_at) if caja.cerrada_at else None,
    }


def _gasto_dict(g: Gasto) -> dict:
    return {
        "id": g.id,
        "caja_id": g.caja_id,
        "punto_id": g.punto_id,
        "categoria": g.categoria,
        "descripcion": g.descripcion,
        "monto": float(g.monto),
        "registrado_por": g.registrado_por,
        "created_at": str(g.created_at),
    }


def _desperdicio_dict(d: Desperdicio) -> dict:
    return {
        "id": d.id,
        "punto_id": d.punto_id,
        "producto_id": d.producto_id,
        "item_inventario_id": d.item_inventario_id,
        "cantidad": float(d.cantidad),
        "unidad": d.unidad,
        "motivo": d.motivo,
        "costo_estimado": float(d.costo_estimado) if d.costo_estimado is not None else None,
        "registrado_por": d.registrado_por,
        "created_at": str(d.created_at),
    }


def _item_dict(i: ItemInventario) -> dict:
    return {
        "id": i.id,
        "punto_id": i.punto_id,
        "nombre": i.nombre,
        "tipo": i.tipo,
        "unidad": i.unidad,
        "producto_menu_id": i.producto_menu_id,
        "orden_conteo": i.orden_conteo,
        "activo": i.activo,
    }


def _fondo_dict(f: FondoRepartidor) -> dict:
    return {
        "id": f.id,
        "caja_id": f.caja_id,
        "repartidor_id": f.repartidor_id,
        "monto_entregado": float(f.monto_entregado),
        "monto_liquidado": float(f.monto_liquidado) if f.monto_liquidado is not None else None,
        "diferencia": float(f.diferencia) if f.diferencia is not None else None,
        "estado": f.estado,
        "entregado_at": str(f.entregado_at),
        "liquidado_at": str(f.liquidado_at) if f.liquidado_at else None,
    }


def _calcular_efectivo_esperado(session, caja: CajaDiaria) -> Decimal:
    day_start, day_end = _day_bounds(caja.fecha)

    ventas_efectivo = session.execute(
        select(func.coalesce(func.sum(TransaccionVenta.precio_venta), 0)).where(
            TransaccionVenta.punto_id == caja.punto_id,
            TransaccionVenta.metodo_pago == "efectivo",
            TransaccionVenta.created_at >= day_start,
            TransaccionVenta.created_at < day_end,
        )
    ).scalar_one()

    gastos_total = session.execute(
        select(func.coalesce(func.sum(Gasto.monto), 0)).where(Gasto.caja_id == caja.id)
    ).scalar_one()

    fondos_pendientes = session.execute(
        select(func.coalesce(func.sum(FondoRepartidor.monto_entregado), 0)).where(
            FondoRepartidor.caja_id == caja.id,
            FondoRepartidor.monto_liquidado.is_(None),
        )
    ).scalar_one()

    fondos_liquidados_hoy = session.execute(
        select(func.coalesce(func.sum(FondoRepartidor.monto_liquidado), 0)).where(
            FondoRepartidor.caja_id == caja.id,
            FondoRepartidor.liquidado_at >= day_start,
            FondoRepartidor.liquidado_at < day_end,
        )
    ).scalar_one()

    return (
        Decimal(str(caja.fondo_inicial))
        + Decimal(str(ventas_efectivo))
        - Decimal(str(gastos_total))
        - Decimal(str(fondos_pendientes))
        + Decimal(str(fondos_liquidados_hoy))
    )


def _lookup_costo_unitario(session, punto_id: int, nombre: str) -> Optional[Decimal]:
    """Best-effort: no hay catálogo canónico de costos, así que se usa el
    costo_unitario más reciente registrado en una venta con el mismo nombre de item."""
    recientes = session.execute(
        select(TransaccionVenta.items_json)
        .where(TransaccionVenta.punto_id == punto_id)
        .order_by(TransaccionVenta.created_at.desc())
        .limit(50)
    ).scalars().all()
    nombre_lower = nombre.strip().lower()
    for items_json in recientes:
        for item in items_json or []:
            if str(item.get("nombre", "")).strip().lower() == nombre_lower:
                costo = item.get("costo_unitario")
                if costo:
                    return Decimal(str(costo))
    return None


# ---------------------------------------------------------------------------
# Caja diaria
# ---------------------------------------------------------------------------


@router.post("/caja/abrir")
def abrir_caja(
    body: CajaDiariaCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        hoy = date.today()
        existente = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == current_user.punto_id,
                CajaDiaria.fecha == hoy,
            )
        ).scalars().first()
        if existente:
            raise HTTPException(status_code=400, detail="Ya existe una caja para hoy en este punto de venta")

        caja = CajaDiaria(
            punto_id=current_user.punto_id,
            fecha=hoy,
            fondo_inicial=body.fondo_inicial,
            estado="abierta",
            abierta_por=current_user.user_id,
        )
        session.add(caja)
        session.flush()

        inv_apertura = InventarioDiario(
            caja_id=caja.id,
            punto_id=current_user.punto_id,
            fecha=hoy,
            momento="apertura",
            registrado_por=current_user.user_id,
            completado=False,
        )
        session.add(inv_apertura)
        session.flush()

        # Pre-llenar con el cierre del día anterior, si existe
        ayer = hoy - timedelta(days=1)
        caja_ayer = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == current_user.punto_id,
                CajaDiaria.fecha == ayer,
            )
        ).scalars().first()
        if caja_ayer:
            inv_cierre_ayer = session.execute(
                select(InventarioDiario).where(
                    InventarioDiario.caja_id == caja_ayer.id,
                    InventarioDiario.momento == "cierre",
                )
            ).scalars().first()
            if inv_cierre_ayer:
                detalle_ayer = session.execute(
                    select(InventarioDetalle).where(
                        InventarioDetalle.inventario_id == inv_cierre_ayer.id
                    )
                ).scalars().all()
                for d in detalle_ayer:
                    session.add(
                        InventarioDetalle(
                            inventario_id=inv_apertura.id,
                            item_id=d.item_id,
                            cantidad=d.cantidad,
                        )
                    )

        registrar_auditoria(
            session,
            accion="ABRIR_CAJA",
            entidad="caja_diaria",
            entidad_id=caja.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"fondo_inicial": float(body.fondo_inicial)},
        )
        session.commit()
        return _caja_dict(caja)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/caja/actual")
def caja_actual(current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA))):
    session = Session()
    try:
        caja = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == current_user.punto_id,
                CajaDiaria.fecha == date.today(),
            )
        ).scalars().first()
        if not caja:
            raise HTTPException(status_code=404, detail="No hay caja registrada hoy")

        gastos_hoy = session.execute(
            select(func.coalesce(func.sum(Gasto.monto), 0)).where(Gasto.caja_id == caja.id)
        ).scalar_one()
        fondos_entregados = session.execute(
            select(func.coalesce(func.sum(FondoRepartidor.monto_entregado), 0)).where(
                FondoRepartidor.caja_id == caja.id,
                FondoRepartidor.monto_liquidado.is_(None),
            )
        ).scalar_one()

        return {
            "id": caja.id,
            "fondo_inicial": float(caja.fondo_inicial),
            "gastos_hoy": float(gastos_hoy),
            "fondos_entregados": float(fondos_entregados),
            "estado": caja.estado,
            "efectivo_esperado": float(caja.efectivo_esperado) if caja.efectivo_esperado is not None else None,
            "efectivo_contado": float(caja.efectivo_contado) if caja.efectivo_contado is not None else None,
            "descuadre": float(caja.descuadre) if caja.descuadre is not None else None,
        }
    except HTTPException:
        raise
    finally:
        session.close()


@router.post("/caja/cerrar")
def cerrar_caja(
    body: CajaDiariaCerrarRequest,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        caja = _get_caja_abierta(session, current_user.punto_id)

        inv_cierre = session.execute(
            select(InventarioDiario).where(
                InventarioDiario.caja_id == caja.id,
                InventarioDiario.momento == "cierre",
            )
        ).scalars().first()
        if not inv_cierre or not inv_cierre.completado:
            raise HTTPException(
                status_code=400,
                detail="Debe completar el conteo de inventario de cierre antes de cerrar la caja",
            )

        efectivo_esperado = _calcular_efectivo_esperado(session, caja)
        descuadre = body.efectivo_contado - efectivo_esperado

        caja.efectivo_esperado = efectivo_esperado
        caja.efectivo_contado = body.efectivo_contado
        caja.descuadre = descuadre
        caja.estado = "cerrada"
        caja.cerrada_por = current_user.user_id
        caja.cerrada_at = datetime.utcnow()

        registrar_auditoria(
            session,
            accion="CERRAR_CAJA",
            entidad="caja_diaria",
            entidad_id=caja.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={
                "efectivo_esperado": float(efectivo_esperado),
                "efectivo_contado": float(body.efectivo_contado),
                "descuadre": float(descuadre),
            },
        )
        session.commit()
        return _caja_dict(caja)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------


@router.post("/gastos")
def registrar_gasto(
    body: GastoCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        caja = _get_caja_abierta(session, current_user.punto_id)
        gasto = Gasto(
            caja_id=caja.id,
            punto_id=current_user.punto_id,
            categoria=body.categoria.value,
            descripcion=body.descripcion,
            monto=body.monto,
            registrado_por=current_user.user_id,
        )
        session.add(gasto)
        session.flush()

        registrar_auditoria(
            session,
            accion="REGISTRAR_GASTO",
            entidad="gasto",
            entidad_id=gasto.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"categoria": body.categoria.value, "monto": float(body.monto)},
        )
        session.commit()
        return _gasto_dict(gasto)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/gastos")
def listar_gastos(
    fecha: Optional[date] = Query(default=None),
    categoria: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        stmt = select(Gasto).where(Gasto.punto_id == current_user.punto_id)
        if fecha:
            day_start, day_end = _day_bounds(fecha)
            stmt = stmt.where(Gasto.created_at >= day_start, Gasto.created_at < day_end)
        if categoria:
            stmt = stmt.where(Gasto.categoria == categoria)
        gastos = session.execute(stmt.order_by(Gasto.created_at.desc())).scalars().all()
        return [_gasto_dict(g) for g in gastos]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Desperdicios
# ---------------------------------------------------------------------------


@router.post("/desperdicios")
def registrar_desperdicio(
    body: DesperdicioCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        costo_estimado = None
        if body.item_inventario_id:
            item = session.get(ItemInventario, body.item_inventario_id)
            if item:
                costo_unitario = _lookup_costo_unitario(session, current_user.punto_id, item.nombre)
                if costo_unitario is not None:
                    costo_estimado = Decimal(str(body.cantidad)) * costo_unitario

        desperdicio = Desperdicio(
            punto_id=current_user.punto_id,
            producto_id=body.producto_id,
            item_inventario_id=body.item_inventario_id,
            cantidad=body.cantidad,
            unidad=body.unidad,
            motivo=body.motivo,
            costo_estimado=costo_estimado,
            registrado_por=current_user.user_id,
        )
        session.add(desperdicio)
        session.flush()

        registrar_auditoria(
            session,
            accion="REGISTRAR_DESPERDICIO",
            entidad="desperdicio",
            entidad_id=desperdicio.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"cantidad": body.cantidad, "unidad": body.unidad},
        )
        session.commit()
        return _desperdicio_dict(desperdicio)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/desperdicios")
def listar_desperdicios(
    fecha: Optional[date] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        stmt = select(Desperdicio).where(Desperdicio.punto_id == current_user.punto_id)
        if fecha:
            day_start, day_end = _day_bounds(fecha)
            stmt = stmt.where(Desperdicio.created_at >= day_start, Desperdicio.created_at < day_end)
        desperdicios = session.execute(stmt.order_by(Desperdicio.created_at.desc())).scalars().all()
        return [_desperdicio_dict(d) for d in desperdicios]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Items de inventario
# ---------------------------------------------------------------------------


@router.post("/inventario/items")
def crear_item_inventario(
    body: ItemInventarioCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        item = ItemInventario(
            punto_id=current_user.punto_id,
            nombre=body.nombre,
            tipo=body.tipo.value,
            unidad=body.unidad,
            producto_menu_id=body.producto_menu_id,
            orden_conteo=body.orden_conteo,
            activo=True,
        )
        session.add(item)
        session.commit()
        return _item_dict(item)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.put("/inventario/items/{item_id}")
def actualizar_item_inventario(
    item_id: int,
    body: ItemInventarioUpdate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        item = session.get(ItemInventario, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        updates = body.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if field == "tipo" and value is not None:
                value = value.value if hasattr(value, "value") else value
            setattr(item, field, value)
        session.commit()
        return _item_dict(item)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/inventario/items")
def listar_items_inventario(
    # Catálogo, no información sensible - también accesible a gerente_central
    # (lo necesita para el selector de item en /central/reglas), sin ampliar
    # _ROLES_TIENDA global (que también protege caja/gastos/desperdicios).
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA, "gerente_central")),
):
    session = Session()
    try:
        items = session.execute(
            select(ItemInventario)
            .where(ItemInventario.activo.is_(True))
            .order_by(ItemInventario.orden_conteo)
        ).scalars().all()
        return [_item_dict(i) for i in items]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Inventario diario (apertura / cierre)
# ---------------------------------------------------------------------------


def _submit_inventario(session, current_user: TokenData, momento: str, body: InventarioDiarioSubmit) -> InventarioDiario:
    caja = _get_caja_abierta(session, current_user.punto_id)
    hoy = date.today()

    inv = session.execute(
        select(InventarioDiario).where(
            InventarioDiario.caja_id == caja.id,
            InventarioDiario.momento == momento,
        )
    ).scalars().first()
    if not inv:
        inv = InventarioDiario(
            caja_id=caja.id,
            punto_id=current_user.punto_id,
            fecha=hoy,
            momento=momento,
            registrado_por=current_user.user_id,
            completado=False,
        )
        session.add(inv)
        session.flush()

    existentes = {
        d.item_id: d
        for d in session.execute(
            select(InventarioDetalle).where(InventarioDetalle.inventario_id == inv.id)
        ).scalars().all()
    }
    for entry in body.items:
        if entry.item_id in existentes:
            existentes[entry.item_id].cantidad = entry.cantidad
        else:
            session.add(
                InventarioDetalle(inventario_id=inv.id, item_id=entry.item_id, cantidad=entry.cantidad)
            )

    inv.completado = True
    session.flush()
    return inv


def _inventario_dict(session, inv: InventarioDiario) -> dict:
    detalle = session.execute(
        select(InventarioDetalle, ItemInventario)
        .join(ItemInventario, ItemInventario.id == InventarioDetalle.item_id)
        .where(InventarioDetalle.inventario_id == inv.id)
    ).all()
    return {
        "id": inv.id,
        "caja_id": inv.caja_id,
        "punto_id": inv.punto_id,
        "fecha": str(inv.fecha),
        "momento": inv.momento,
        "completado": inv.completado,
        "detalle": [
            {"item_id": d.item_id, "nombre": i.nombre, "unidad": i.unidad, "cantidad": float(d.cantidad)}
            for d, i in detalle
        ],
    }


@router.get("/inventario/diario/{momento}")
def get_inventario_diario(
    momento: str,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    if momento not in ("apertura", "cierre"):
        raise HTTPException(status_code=400, detail="Momento inválido")
    session = Session()
    try:
        caja = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == current_user.punto_id,
                CajaDiaria.fecha == date.today(),
            )
        ).scalars().first()
        if not caja:
            return {"completado": False, "detalle": []}

        inv = session.execute(
            select(InventarioDiario).where(
                InventarioDiario.caja_id == caja.id,
                InventarioDiario.momento == momento,
            )
        ).scalars().first()
        if not inv:
            return {"completado": False, "detalle": []}
        return _inventario_dict(session, inv)
    finally:
        session.close()


@router.post("/inventario/diario/apertura")
def submit_inventario_apertura(
    body: InventarioDiarioSubmit,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        inv = _submit_inventario(session, current_user, "apertura", body)
        session.commit()
        return _inventario_dict(session, inv)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.post("/inventario/diario/cierre")
def submit_inventario_cierre(
    body: InventarioDiarioSubmit,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        inv = _submit_inventario(session, current_user, "cierre", body)
        session.commit()
        return _inventario_dict(session, inv)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


def _calcular_consumo(session, punto_id: int, fecha: date) -> list:
    day_start, day_end = _day_bounds(fecha)

    items = session.execute(
        select(ItemInventario)
        .where(ItemInventario.activo.is_(True))
        .order_by(ItemInventario.orden_conteo)
    ).scalars().all()

    def _detalle_map(momento: str) -> dict:
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

    apertura_map = _detalle_map("apertura")
    cierre_map = _detalle_map("cierre")

    desperdicio_rows = session.execute(
        select(Desperdicio.item_inventario_id, func.coalesce(func.sum(Desperdicio.cantidad), 0))
        .where(
            Desperdicio.punto_id == punto_id,
            Desperdicio.created_at >= day_start,
            Desperdicio.created_at < day_end,
            Desperdicio.item_inventario_id.isnot(None),
        )
        .group_by(Desperdicio.item_inventario_id)
    ).all()
    desperdicio_map = {item_id: Decimal(str(total)) for item_id, total in desperdicio_rows}

    recibido_rows = session.execute(
        select(TransaccionPedido.items_json).where(
            TransaccionPedido.punto_id == punto_id,
            TransaccionPedido.tipo == "recepcion_central",
            TransaccionPedido.estado == "completada",
            TransaccionPedido.completado_at >= day_start,
            TransaccionPedido.completado_at < day_end,
        )
    ).scalars().all()
    recibido_map: dict = {}
    for items_json in recibido_rows:
        for entry in items_json or []:
            item_id = entry.get("item_id")
            cantidad = Decimal(str(entry.get("cantidad", 0)))
            recibido_map[item_id] = recibido_map.get(item_id, Decimal("0")) + cantidad

    ventas = session.execute(
        select(TransaccionVenta.items_json).where(
            TransaccionVenta.punto_id == punto_id,
            TransaccionVenta.created_at >= day_start,
            TransaccionVenta.created_at < day_end,
            TransaccionVenta.estado == "completada",
        )
    ).scalars().all()
    # No existe un catálogo canónico de productos vendidos por id: el cruce con
    # ventas se hace por nombre de item (normalizado), ya que items_json solo guarda nombre.
    teorico_map: dict = {}
    for items_json in ventas:
        for entry in items_json or []:
            nombre = str(entry.get("nombre", "")).strip().lower()
            cantidad = Decimal(str(entry.get("cantidad", 0)))
            teorico_map[nombre] = teorico_map.get(nombre, Decimal("0")) + cantidad

    resultado = []
    for item in items:
        apertura = apertura_map.get(item.id, Decimal("0"))
        cierre = cierre_map.get(item.id, Decimal("0"))
        desperdicio = desperdicio_map.get(item.id, Decimal("0"))
        recibido = recibido_map.get(item.id, Decimal("0"))
        consumo_real = apertura + recibido - cierre - desperdicio
        consumo_teorico = teorico_map.get(item.nombre.strip().lower(), Decimal("0"))
        diferencia = abs(consumo_real - consumo_teorico)
        resultado.append(
            {
                "item_id": item.id,
                "nombre": item.nombre,
                "apertura": float(apertura),
                "recibido_envios": float(recibido),
                "cierre": float(cierre),
                "desperdicio": float(desperdicio),
                "consumo_real": float(consumo_real),
                "consumo_teorico": float(consumo_teorico),
                "diferencia": float(diferencia),
            }
        )
    return resultado


@router.get("/inventario/consumo")
def reporte_consumo(
    fecha: date = Query(...),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        return {
            "fecha": str(fecha),
            "items": _calcular_consumo(session, current_user.punto_id, fecha),
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Fondos de repartidor
# ---------------------------------------------------------------------------


@router.post("/fondos-repartidor")
def entregar_fondo_repartidor(
    body: FondoRepartidorCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        caja = _get_caja_abierta(session, current_user.punto_id)
        fondo = FondoRepartidor(
            caja_id=caja.id,
            repartidor_id=body.repartidor_id,
            monto_entregado=body.monto_entregado,
            estado="entregado",
        )
        session.add(fondo)
        session.flush()

        registrar_auditoria(
            session,
            accion="ENTREGAR_FONDO_REPARTIDOR",
            entidad="fondo_repartidor",
            entidad_id=fondo.id,
            usuario_id=current_user.user_id,
            punto_id=current_user.punto_id,
            detalle={"repartidor_id": body.repartidor_id, "monto_entregado": float(body.monto_entregado)},
        )
        session.commit()
        return _fondo_dict(fondo)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.get("/fondos-repartidor")
def listar_fondos_repartidor(current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA))):
    session = Session()
    try:
        caja = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == current_user.punto_id,
                CajaDiaria.fecha == date.today(),
            )
        ).scalars().first()
        if not caja:
            return []
        fondos = session.execute(
            select(FondoRepartidor)
            .where(FondoRepartidor.caja_id == caja.id)
            .order_by(FondoRepartidor.entregado_at.desc())
        ).scalars().all()
        return [_fondo_dict(f) for f in fondos]
    finally:
        session.close()


@router.post("/fondos-repartidor/{fondo_id}/liquidar")
def liquidar_fondo_repartidor(
    fondo_id: int,
    body: FondoRepartidorLiquidarRequest,
    current_user: TokenData = Depends(requiere_rol("repartidor", *_ROLES_TIENDA)),
):
    session = Session()
    try:
        fondo = session.get(FondoRepartidor, fondo_id)
        if not fondo:
            raise HTTPException(status_code=404, detail="Fondo no encontrado")
        if current_user.rol == "repartidor" and fondo.repartidor_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Solo puede liquidar su propio fondo")
        if fondo.estado == "liquidado":
            raise HTTPException(status_code=400, detail="Este fondo ya fue liquidado")

        fondo.monto_liquidado = body.monto_liquidado
        fondo.diferencia = body.monto_liquidado - fondo.monto_entregado
        fondo.estado = "liquidado"
        fondo.liquidado_at = datetime.utcnow()

        registrar_auditoria(
            session,
            accion="LIQUIDAR_FONDO_REPARTIDOR",
            entidad="fondo_repartidor",
            entidad_id=fondo.id,
            usuario_id=current_user.user_id,
            detalle={
                "monto_entregado": float(fondo.monto_entregado),
                "monto_liquidado": float(body.monto_liquidado),
                "diferencia": float(fondo.diferencia),
            },
        )
        session.commit()
        return _fondo_dict(fondo)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Transacciones de pedidos (compras a proveedor / envíos con central)
# ---------------------------------------------------------------------------


@router.post("/pedidos")
def crear_transaccion_pedido(
    body: TransaccionPedidoCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        pedido = TransaccionPedido(
            punto_id=current_user.punto_id,
            tipo=body.tipo,
            items_json=[item.model_dump() for item in body.items],
            estado="pendiente",
            creado_por=current_user.user_id,
        )
        session.add(pedido)
        session.commit()
        return {
            "id": pedido.id,
            "punto_id": pedido.punto_id,
            "tipo": pedido.tipo,
            "items_json": pedido.items_json,
            "estado": pedido.estado,
            "creado_por": pedido.creado_por,
            "created_at": str(pedido.created_at),
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.put("/pedidos/{pedido_id}/completar")
def completar_transaccion_pedido(
    pedido_id: int,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    session = Session()
    try:
        pedido = session.get(TransaccionPedido, pedido_id)
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        pedido.estado = "completada"
        pedido.completado_por = current_user.user_id
        pedido.completado_at = datetime.utcnow()
        session.commit()
        return {"id": pedido.id, "estado": pedido.estado}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Reporte de cierre
# ---------------------------------------------------------------------------


@router.get("/caja/reporte-cierre")
def reporte_cierre(
    fecha: date = Query(...),
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*_ROLES_TIENDA)),
):
    effective_punto_id = _resolve_punto_id(current_user, punto_id)

    session = Session()
    try:
        caja = session.execute(
            select(CajaDiaria).where(
                CajaDiaria.punto_id == effective_punto_id,
                CajaDiaria.fecha == fecha,
            )
        ).scalars().first()
        if not caja:
            raise HTTPException(status_code=404, detail="No hay caja registrada para esa fecha")

        gastos = session.execute(
            select(Gasto).where(Gasto.caja_id == caja.id)
        ).scalars().all()
        day_start, day_end = _day_bounds(fecha)
        desperdicios = session.execute(
            select(Desperdicio).where(
                Desperdicio.punto_id == effective_punto_id,
                Desperdicio.created_at >= day_start,
                Desperdicio.created_at < day_end,
            )
        ).scalars().all()
        fondos = session.execute(
            select(FondoRepartidor).where(FondoRepartidor.caja_id == caja.id)
        ).scalars().all()
        consumo = _calcular_consumo(session, effective_punto_id, fecha)

        total_ventas = session.execute(
            select(func.coalesce(func.sum(TransaccionVenta.precio_venta), 0)).where(
                TransaccionVenta.punto_id == effective_punto_id,
                TransaccionVenta.created_at >= day_start,
                TransaccionVenta.created_at < day_end,
                TransaccionVenta.estado == "completada",
            )
        ).scalar_one()
        total_gastos = sum(float(g.monto) for g in gastos)
        total_desperdicios = sum(float(d.costo_estimado) for d in desperdicios if d.costo_estimado is not None)
        total_fondos = sum(float(f.monto_entregado) for f in fondos)
        total_margen_bruto = float(total_ventas) - total_gastos - total_desperdicios

        return {
            "caja": _caja_dict(caja),
            "gastos": [_gasto_dict(g) for g in gastos],
            "desperdicios": [_desperdicio_dict(d) for d in desperdicios],
            "fondos_repartidor": [_fondo_dict(f) for f in fondos],
            "consumo": consumo,
            "resumen": {
                "total_ventas": round(float(total_ventas), 2),
                "total_gastos": round(total_gastos, 2),
                "total_desperdicios": round(total_desperdicios, 2),
                "total_fondos": round(total_fondos, 2),
                "total_margen_bruto": round(total_margen_bruto, 2),
                "total_merma": round(sum(c["diferencia"] for c in consumo), 2),
            },
        }
    except HTTPException:
        raise
    finally:
        session.close()
