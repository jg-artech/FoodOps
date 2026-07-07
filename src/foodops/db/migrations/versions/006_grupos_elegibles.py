"""Opción B: grupos elegibles formales en producto_componentes.

Antes, "elegible" era un booleano plano sin forma de distinguir dos slots de
elección independientes en el mismo producto (p.ej. ¼ Pollo necesita elegir
tanto la pieza como la guarnición por separado). Se agrega grupo_elegible
(entero, agrupa componentes de un mismo producto que forman un "elige 1") y
nombre_grupo (label para la UI).

Data migration: el producto real ¼ Pollo (productos_menu.id=3) ya tenía un
grupo elegible sin formalizar (la guarnición, 4 opciones). Se le asigna
grupo_elegible=2 "Guarnición" y se agrega un nuevo grupo 1 "Pieza de Pollo"
(Pechuga+Ala / Cuadril+Pierna), creando primero los items_inventario
correspondientes ya que no existían (los ids 52/53 de la spec original ya
están tomados por Jalapeño/Cebolla en la data real).

Revision ID: 006_grupos_elegibles
Revises: 005_productos_menu_crud
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "006_grupos_elegibles"
down_revision = "005_productos_menu_crud"
branch_labels = None
depends_on = None

_PRODUCTO_CUARTO_POLLO_ID = 3
_GRUPO_PIEZA = 1
_NOMBRE_GRUPO_PIEZA = "Pieza de Pollo"
_GRUPO_GUARNICION = 2
_NOMBRE_GRUPO_GUARNICION = "Guarnición"
_ITEMS_GUARNICION_EXISTENTES = (54, 55, 56, 57)


def upgrade() -> None:
    op.add_column("producto_componentes", sa.Column("grupo_elegible", sa.Integer(), nullable=True))
    op.add_column("producto_componentes", sa.Column("nombre_grupo", sa.String(100), nullable=True))
    op.create_index(
        "idx_producto_componentes_grupo",
        "producto_componentes",
        ["producto_menu_id", "grupo_elegible"],
    )

    conn = op.get_bind()

    # Backfill: la guarnición de ¼ Pollo ya existía como elegible=true sin grupo formal.
    conn.execute(
        sa.text(
            """
            UPDATE producto_componentes
            SET grupo_elegible = :grupo, nombre_grupo = :nombre
            WHERE producto_menu_id = :producto_id
              AND item_inventario_id = ANY(:items)
            """
        ),
        {
            "grupo": _GRUPO_GUARNICION,
            "nombre": _NOMBRE_GRUPO_GUARNICION,
            "producto_id": _PRODUCTO_CUARTO_POLLO_ID,
            "items": list(_ITEMS_GUARNICION_EXISTENTES),
        },
    )

    # Nuevo grupo "Pieza de Pollo": crear los items_inventario (no existían) y
    # las filas de receta elegibles para el producto ¼ Pollo.
    orden_base = conn.execute(
        sa.text("SELECT COALESCE(MAX(orden_conteo), 0) FROM items_inventario")
    ).scalar()

    pechuga_id = conn.execute(
        sa.text(
            """
            INSERT INTO items_inventario (nombre, tipo, unidad, orden_conteo, activo)
            VALUES ('Pechuga+Ala (porción)', 'insumo', 'porcion', :orden, true)
            RETURNING id
            """
        ),
        {"orden": orden_base + 1},
    ).scalar()

    cuadril_id = conn.execute(
        sa.text(
            """
            INSERT INTO items_inventario (nombre, tipo, unidad, orden_conteo, activo)
            VALUES ('Cuadril+Pierna (porción)', 'insumo', 'porcion', :orden, true)
            RETURNING id
            """
        ),
        {"orden": orden_base + 2},
    ).scalar()

    for item_id in (pechuga_id, cuadril_id):
        conn.execute(
            sa.text(
                """
                INSERT INTO producto_componentes
                    (producto_menu_id, item_inventario_id, cantidad, elegible, grupo_elegible, nombre_grupo)
                VALUES (:producto_id, :item_id, 1, true, :grupo, :nombre)
                """
            ),
            {
                "producto_id": _PRODUCTO_CUARTO_POLLO_ID,
                "item_id": item_id,
                "grupo": _GRUPO_PIEZA,
                "nombre": _NOMBRE_GRUPO_PIEZA,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    item_ids = conn.execute(
        sa.text(
            """
            SELECT item_inventario_id FROM producto_componentes
            WHERE producto_menu_id = :producto_id AND grupo_elegible = :grupo
            """
        ),
        {"producto_id": _PRODUCTO_CUARTO_POLLO_ID, "grupo": _GRUPO_PIEZA},
    ).scalars().all()

    conn.execute(
        sa.text(
            """
            DELETE FROM producto_componentes
            WHERE producto_menu_id = :producto_id AND grupo_elegible = :grupo
            """
        ),
        {"producto_id": _PRODUCTO_CUARTO_POLLO_ID, "grupo": _GRUPO_PIEZA},
    )
    if item_ids:
        conn.execute(
            sa.text("DELETE FROM items_inventario WHERE id = ANY(:ids)"),
            {"ids": list(item_ids)},
        )

    conn.execute(
        sa.text(
            """
            UPDATE producto_componentes
            SET grupo_elegible = NULL, nombre_grupo = NULL
            WHERE producto_menu_id = :producto_id
              AND item_inventario_id = ANY(:items)
            """
        ),
        {"producto_id": _PRODUCTO_CUARTO_POLLO_ID, "items": list(_ITEMS_GUARNICION_EXISTENTES)},
    )

    op.drop_index("idx_producto_componentes_grupo", table_name="producto_componentes")
    op.drop_column("producto_componentes", "nombre_grupo")
    op.drop_column("producto_componentes", "grupo_elegible")
