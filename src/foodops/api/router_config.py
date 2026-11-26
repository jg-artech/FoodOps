"""CRUD de catálogo de productos + receta (producto_componentes), desde ConfigView"""
import logging

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import TokenData, exigir_acceso_a_punto, requiere_rol, resolver_punto_id
from foodops.core.config import settings
from foodops.core.permisos_ordenes import (
    ROLES_ADMINISTRAR_PERSONAL_COCINA,
    ROLES_VER_PERSONAL_COCINA,
)
from foodops.db.models import PersonalCocina
from foodops.db.models_caja import ItemInventario
from foodops.db.models_stock import ProductoComponente, ProductoMenu
from foodops.domain.schemas import PersonalCocinaCreate, PersonalCocinaUpdate
from foodops.domain.schemas_stock import (
    ProductoConComponentesCreate,
    ProductoConComponentesUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_ROLES_GERENCIA = ("gerente_general", "admin")


def _normalizar_contenido(contenido):
    """Recorta espacios; un contenido vacío se guarda como NULL (no se muestra)."""
    if contenido is None:
        return None
    contenido = contenido.strip()
    return contenido or None


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
        "contenido": producto.contenido,
        "activo": producto.activo,
        "componentes": [
            {
                "item_id": c.item_inventario_id,
                "item_nombre": item.nombre,
                "cantidad": float(c.cantidad),
                "elegible": c.elegible,
                "grupo_elegible": c.grupo_elegible,
                "nombre_grupo": c.nombre_grupo,
                "cantidad_elegible_minima": c.cantidad_elegible_minima,
                "cantidad_elegible_maxima": c.cantidad_elegible_maxima,
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


def _validar_grupos(componentes) -> None:
    """Un mismo número de grupo_elegible dentro del producto debe tener siempre
    el mismo nombre_grupo y el mismo min/máx elegible (evita, p.ej., dos
    componentes en grupo=1 con labels o reglas distintas por error de UI)."""
    specs_por_grupo: dict = {}
    for c in componentes:
        if c.grupo_elegible is None:
            continue
        spec = (c.nombre_grupo, c.cantidad_elegible_minima, c.cantidad_elegible_maxima)
        previo = specs_por_grupo.setdefault(c.grupo_elegible, spec)
        if previo != spec:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Grupo {c.grupo_elegible} tiene configuración inconsistente: "
                    f"nombre/min/máx {previo} vs {spec}"
                ),
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
        _validar_grupos(body.componentes)

        tipo = "combo" if body.categoria == "combos" else "individual"
        producto = ProductoMenu(
            nombre=body.nombre.strip(),
            precio=body.precio,
            categoria=body.categoria,
            tipo=tipo,
            unidad=body.unidad,
            contenido=_normalizar_contenido(body.contenido),
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
                    grupo_elegible=c.grupo_elegible,
                    nombre_grupo=c.nombre_grupo,
                    cantidad_elegible_minima=c.cantidad_elegible_minima,
                    cantidad_elegible_maxima=c.cantidad_elegible_maxima,
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
        _validar_grupos(body.componentes)

        producto.nombre = body.nombre.strip()
        producto.precio = body.precio
        producto.categoria = body.categoria
        producto.tipo = "combo" if body.categoria == "combos" else "individual"
        producto.unidad = body.unidad
        # Solo si el cliente lo envió: un PATCH sin contenido no lo borra.
        if "contenido" in body.model_fields_set:
            producto.contenido = _normalizar_contenido(body.contenido)

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
                    grupo_elegible=c.grupo_elegible,
                    nombre_grupo=c.nombre_grupo,
                    cantidad_elegible_minima=c.cantidad_elegible_minima,
                    cantidad_elegible_maxima=c.cantidad_elegible_maxima,
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


# ---------------------------------------------------------------------------
# Personal de cocina por tienda (migración 016). Sin DELETE: hay rotación y
# las órdenes conservan el id de quien las preparó; se desactiva con PATCH.
# ---------------------------------------------------------------------------


def _personal_dict(p: PersonalCocina) -> dict:
    return {
        "id": p.id,
        "punto_id": p.punto_id,
        "nombre": p.nombre,
        "activo": p.activo,
        "created_at": str(p.created_at),
    }


def _validar_nombre_personal_unico(session, punto_id: int, nombre: str, excluir_id: int = None) -> None:
    stmt = select(PersonalCocina).where(
        PersonalCocina.punto_id == punto_id,
        func.lower(PersonalCocina.nombre) == nombre.lower(),
    )
    if excluir_id is not None:
        stmt = stmt.where(PersonalCocina.id != excluir_id)
    if session.execute(stmt).scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe '{nombre}' en el personal de cocina de esta tienda (activo o inactivo)",
        )


@router.get("/personal-cocina")
def listar_personal_cocina(
    punto_id: Optional[int] = Query(default=None),
    incluir_inactivos: bool = Query(default=False),
    current_user: TokenData = Depends(requiere_rol(*ROLES_VER_PERSONAL_COCINA)),
):
    """Personal de una tienda. Cocina lo usa para el selector de responsable
    (solo activos); los inactivos solo los ve quien administra el personal."""
    session = Session()
    try:
        punto = resolver_punto_id(session, current_user, punto_id)
        stmt = select(PersonalCocina).where(PersonalCocina.punto_id == punto)
        if not (incluir_inactivos and current_user.rol in ROLES_ADMINISTRAR_PERSONAL_COCINA):
            stmt = stmt.where(PersonalCocina.activo.is_(True))
        filas = session.execute(
            stmt.order_by(PersonalCocina.activo.desc(), func.lower(PersonalCocina.nombre))
        ).scalars().all()
        return [_personal_dict(p) for p in filas]
    finally:
        session.close()


@router.post("/personal-cocina", status_code=201)
def crear_personal_cocina(
    body: PersonalCocinaCreate,
    current_user: TokenData = Depends(requiere_rol(*ROLES_ADMINISTRAR_PERSONAL_COCINA)),
):
    session = Session()
    try:
        punto = resolver_punto_id(session, current_user, body.punto_id)
        _validar_nombre_personal_unico(session, punto, body.nombre)
        persona = PersonalCocina(punto_id=punto, nombre=body.nombre, activo=True)
        session.add(persona)
        session.flush()
        registrar_auditoria(
            session,
            accion="PERSONAL_COCINA_CREADO",
            entidad="personal_cocina",
            entidad_id=persona.id,
            usuario_id=current_user.user_id,
            punto_id=punto,
            detalle={"nombre": persona.nombre},
        )
        session.commit()
        return _personal_dict(persona)
    except HTTPException:
        session.rollback()
        raise
    finally:
        session.close()


@router.patch("/personal-cocina/{personal_id}")
def actualizar_personal_cocina(
    personal_id: int,
    body: PersonalCocinaUpdate,
    current_user: TokenData = Depends(requiere_rol(*ROLES_ADMINISTRAR_PERSONAL_COCINA)),
):
    """Cambia el nombre o activa/desactiva. Desactivar no toca las órdenes que
    ya tienen a esta persona como responsable."""
    session = Session()
    try:
        persona = session.get(PersonalCocina, personal_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Personal no encontrado")
        exigir_acceso_a_punto(current_user, persona.punto_id)
        antes = {"nombre": persona.nombre, "activo": persona.activo}
        if body.nombre is not None and body.nombre != persona.nombre:
            _validar_nombre_personal_unico(session, persona.punto_id, body.nombre, excluir_id=persona.id)
            persona.nombre = body.nombre
        if body.activo is not None:
            persona.activo = body.activo
        despues = {"nombre": persona.nombre, "activo": persona.activo}
        if despues != antes:
            registrar_auditoria(
                session,
                accion="PERSONAL_COCINA_ACTUALIZADO",
                entidad="personal_cocina",
                entidad_id=persona.id,
                usuario_id=current_user.user_id,
                punto_id=persona.punto_id,
                detalle={"antes": antes, "despues": despues},
            )
        session.commit()
        return _personal_dict(persona)
    except HTTPException:
        session.rollback()
        raise
    finally:
        session.close()
