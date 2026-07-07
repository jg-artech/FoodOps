"""CRUD de catálogo de productos + receta (producto_componentes), desde ConfigView"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import TokenData, requiere_rol
from foodops.core.config import settings
from foodops.db.models_caja import ItemInventario
from foodops.db.models_stock import ProductoComponente, ProductoMenu
from foodops.domain.schemas_stock import (
    ProductoConComponentesCreate,
    ProductoConComponentesUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_GERENCIA = ("gerente_general", "admin")


def _producto_dict(session, producto: ProductoMenu) -> dict:
    filas = session.execute(
        select(ProductoComponente, ItemInventario)
        .join(ItemInventario, ItemInventario.id == ProductoComponente.item_inventario_id)
        .where(ProductoComponente.producto_menu_id == producto.id)
    ).all()
    return {
        "id": producto.id,
        "nombre": producto.nombre,
        "precio": float(producto.precio),
        "categoria": producto.categoria,
        "tipo": producto.tipo,
        "unidad": producto.unidad,
        "descripcion": producto.descripcion,
        "activo": producto.activo,
        "componentes": [
            {
                "item_id": c.item_inventario_id,
                "item_nombre": item.nombre,
                "cantidad": float(c.cantidad),
                "elegible": c.elegible,
            }
            for c, item in filas
        ],
    }


def _validar_items_inventario(session, componentes) -> None:
    if not componentes:
        return
    ids_pedidos = {c.item_inventario_id for c in componentes}
    ids_existentes = set(
        session.execute(
            select(ItemInventario.id).where(ItemInventario.id.in_(ids_pedidos))
        ).scalars().all()
    )
    faltantes = ids_pedidos - ids_existentes
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"item_inventario_id inválido(s): {sorted(faltantes)}",
        )


def _validar_nombre_unico(session, nombre: str, excluir_id: int = None) -> None:
    stmt = select(ProductoMenu).where(func.lower(ProductoMenu.nombre) == nombre.strip().lower())
    if excluir_id is not None:
        stmt = stmt.where(ProductoMenu.id != excluir_id)
    if session.execute(stmt).scalars().first():
        raise HTTPException(status_code=400, detail=f"Ya existe un producto llamado '{nombre}'")


@router.get("/productos")
def listar_productos_config(current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA))):
    session = Session()
    try:
        productos = session.execute(
            select(ProductoMenu).where(ProductoMenu.activo.is_(True)).order_by(ProductoMenu.id)
        ).scalars().all()
        return [_producto_dict(session, p) for p in productos]
    finally:
        session.close()


@router.post("/productos", status_code=201)
def crear_producto_config(
    body: ProductoConComponentesCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        _validar_nombre_unico(session, body.nombre)
        _validar_items_inventario(session, body.componentes)

        tipo = "combo" if body.categoria == "combos" else "individual"
        producto = ProductoMenu(
            nombre=body.nombre.strip(),
            precio=body.precio,
            categoria=body.categoria,
            tipo=tipo,
            unidad=body.unidad,
            descripcion=body.descripcion,
            activo=True,
        )
        session.add(producto)
        session.flush()

        for c in body.componentes:
            session.add(
                ProductoComponente(
                    producto_menu_id=producto.id,
                    item_inventario_id=c.item_inventario_id,
                    cantidad=c.cantidad,
                    elegible=c.elegible,
                )
            )

        registrar_auditoria(
            session,
            accion="CREAR_PRODUCTO",
            entidad="producto_menu",
            entidad_id=producto.id,
            usuario_id=current_user.user_id,
            detalle={"nombre": producto.nombre, "componentes": len(body.componentes)},
        )
        session.commit()
        return _producto_dict(session, producto)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.patch("/productos/{producto_id}")
def actualizar_producto_config(
    producto_id: int,
    body: ProductoConComponentesUpdate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GERENCIA)),
):
    session = Session()
    try:
        producto = session.get(ProductoMenu, producto_id)
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        _validar_nombre_unico(session, body.nombre, excluir_id=producto_id)
        _validar_items_inventario(session, body.componentes)

        producto.nombre = body.nombre.strip()
        producto.precio = body.precio
        producto.categoria = body.categoria
        producto.tipo = "combo" if body.categoria == "combos" else "individual"
        producto.unidad = body.unidad
        producto.descripcion = body.descripcion

        session.execute(
            ProductoComponente.__table__.delete().where(
                ProductoComponente.producto_menu_id == producto_id
            )
        )
        for c in body.componentes:
            session.add(
                ProductoComponente(
                    producto_menu_id=producto_id,
                    item_inventario_id=c.item_inventario_id,
                    cantidad=c.cantidad,
                    elegible=c.elegible,
                )
            )

        registrar_auditoria(
            session,
            accion="ACTUALIZAR_PRODUCTO",
            entidad="producto_menu",
            entidad_id=producto.id,
            usuario_id=current_user.user_id,
            detalle={"nombre": producto.nombre, "componentes": len(body.componentes)},
        )
        session.commit()
        return _producto_dict(session, producto)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()
