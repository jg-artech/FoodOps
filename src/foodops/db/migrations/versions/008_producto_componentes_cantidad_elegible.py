"""Combos con múltiples guarniciones: min/máx elegible por grupo.

Hasta ahora un grupo_elegible (ver migración 006) siempre era "elige 1"
implícito: el frontend decidía radio vs checkbox único solo mirando
items.length. Eso no alcanza para un grupo donde el cliente puede elegir
2-4 opciones (p.ej. ¼ Pollo con hasta 4 guarniciones). Se agrega control
explícito por fila: cantidad_elegible_minima / cantidad_elegible_maxima.
Todas las filas de un mismo grupo_elegible deben compartir el mismo min/max
(reforzado en _validar_grupos de router_config.py), igual que ya se exige
para nombre_grupo.

Default 1/1 preserva el comportamiento actual (radio "elige exactamente 1")
para todo grupo existente. Solo el grupo "Guarnición" (grupo_elegible=2) del
¼ Pollo real (productos_menu.id=3) se actualiza a max=4 según el pedido de
negocio de permitir 2-4 guarniciones por combo.

Revision ID: 008_grupo_elegible_min_max
Revises: 007_modulo_d_abastecimiento
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "008_grupo_elegible_min_max"
down_revision = "007_modulo_d_abastecimiento"
branch_labels = None
depends_on = None

_PRODUCTO_CUARTO_POLLO_ID = 3
_GRUPO_GUARNICION = 2
_MAX_GUARNICIONES = 4


def upgrade() -> None:
    op.add_column(
        "producto_componentes",
        sa.Column("cantidad_elegible_minima", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "producto_componentes",
        sa.Column("cantidad_elegible_maxima", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_producto_componentes_min_max",
        "producto_componentes",
        "cantidad_elegible_maxima >= cantidad_elegible_minima",
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE producto_componentes
            SET cantidad_elegible_maxima = :max
            WHERE producto_menu_id = :producto_id
              AND grupo_elegible = :grupo
            """
        ),
        {
            "max": _MAX_GUARNICIONES,
            "producto_id": _PRODUCTO_CUARTO_POLLO_ID,
            "grupo": _GRUPO_GUARNICION,
        },
    )


def downgrade() -> None:
    op.drop_constraint("ck_producto_componentes_min_max", "producto_componentes", type_="check")
    op.drop_column("producto_componentes", "cantidad_elegible_maxima")
    op.drop_column("producto_componentes", "cantidad_elegible_minima")
