"""Módulo D: control diario de inventario + abastecimiento inteligente.

Deliberadamente NO crea las tablas movimientos_inventario / pedidos_abastecimiento
/ pedido_abastecimiento_items del spec original: ese subsistema se solapaba
casi por completo con lo que ya existe (InventarioDiario/InventarioDetalle para
apertura/cierre, PedidoReabastecimiento/PedidoReabastecimientoItem con su flujo
crear→confirmar→recibir). Construirlo aparte habría dejado dos fuentes de
verdad de stock que podían divergir. En su lugar:

- reglas_reabastecimiento SÍ es una tabla nueva (min/máx/factor día no existían).
- pedidos_reabastecimiento se extiende con responsable_tipo + fecha_envio en vez
  de duplicarse: un pedido generado por un responsable de abastecimiento central
  es la misma fila, solo con más contexto de origen.
- El "INGRESA" del día y la recepción ya viven en InventarioDetalle/
  cantidad_recibida - _stock_actual() en router_stock.py ya calcula
  inicio+recibido-consumo, que es exactamente la fórmula del spec.

También agrega el rol GERENTE_CENTRAL (no existía) y responsable_abastecimiento
en items_inventario, clasificando el catálogo real (40 items) - el spec asumía
3 tiendas físicas (Centro/Jordán/Aux); en esta BD solo existe punto_venta id=2
(Local Centro), así que las reglas sembradas son únicamente para esa tienda.

Revision ID: 007_modulo_d_abastecimiento
Revises: 006_grupos_elegibles
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "007_modulo_d_abastecimiento"
down_revision = "006_grupos_elegibles"
branch_labels = None
depends_on = None

_PUNTO_LOCAL_CENTRO = 2

# Clasificación del catálogo real (ver items_inventario) - reconciliada contra
# los ejemplos del spec: Pepsi cae bajo POLLO (igual que en el spec), Mayonesa/
# Salsa bajo DESECHABLE_SALSA (igual que el spec), y las piezas de pollo nuevas
# (Pechuga+Ala/Cuadril+Pierna, ver migración 006) se clasifican como POLLO por
# ser cortes de pollo, no "vegetal" genérico.
_ITEMS_POLLO = [1, 2, 3, 4, 5, 6, 7, 64, 65]
_ITEMS_DESECHABLE = [8, 9, 10, 11, 12, 13, 14]
_ITEMS_SALSA_BOTE = [20, 21]  # Mayonesa, Salsa: envases, no unidades sueltas
_ITEMS_VEGETAL = [15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63]

# (item_id, minimo, maximo, consumo_base) - punto de partida razonable, no
# datos históricos reales (esta BD no tiene ventas suficientes para calibrar
# aún); se ajustan luego vía PATCH /api/reglas-reabastecimiento según venta real.
_REGLAS_POLLO = [
    (1, 5, 20, 8), (2, 5, 20, 8), (3, 15, 60, 25),
    (4, 10, 40, 15), (5, 10, 40, 15), (6, 10, 40, 15), (7, 10, 40, 15),
    (64, 15, 60, 25), (65, 15, 60, 25),
]
_REGLAS_DESECHABLE = [(i, 300, 1000, 400) for i in _ITEMS_DESECHABLE]
_REGLAS_SALSA_BOTE = [(i, 2, 10, 4) for i in _ITEMS_SALSA_BOTE]
_REGLAS_VEGETAL = [(i, 5, 20, 8) for i in _ITEMS_VEGETAL]


def upgrade() -> None:
    op.execute("ALTER TYPE userrol ADD VALUE IF NOT EXISTS 'GERENTE_CENTRAL' AFTER 'GERENTE_GENERAL'")

    op.add_column("items_inventario", sa.Column("responsable_abastecimiento", sa.String(30), nullable=True))
    op.create_check_constraint(
        "ck_items_inventario_responsable_abastecimiento",
        "items_inventario",
        "responsable_abastecimiento IN ('POLLO', 'VEGETAL', 'DESECHABLE_SALSA')",
    )

    op.add_column("pedidos_reabastecimiento", sa.Column("responsable_tipo", sa.String(30), nullable=True))
    op.create_check_constraint(
        "ck_pedidos_reab_responsable_tipo",
        "pedidos_reabastecimiento",
        "responsable_tipo IN ('POLLO', 'VEGETAL', 'DESECHABLE_SALSA')",
    )
    op.add_column("pedidos_reabastecimiento", sa.Column("fecha_envio", sa.Date(), nullable=True))
    op.create_index(
        "idx_pedidos_reab_responsable_estado",
        "pedidos_reabastecimiento",
        ["responsable_tipo", "estado"],
    )

    op.create_table(
        "reglas_reabastecimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_inventario_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=False),
        sa.Column("punto_venta_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=True),
        sa.Column("stock_minimo", sa.Numeric(10, 2), nullable=False),
        sa.Column("stock_maximo", sa.Numeric(10, 2), nullable=False),
        sa.Column("consumo_diario_base", sa.Numeric(10, 2), nullable=True),
        sa.Column("factor_sabado", sa.Numeric(3, 2), nullable=False, server_default="1.30"),
        sa.Column("factor_domingo", sa.Numeric(3, 2), nullable=False, server_default="1.50"),
        sa.Column("cantidad_fija_diaria", sa.Numeric(10, 2), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("item_inventario_id", "punto_venta_id", name="uq_reglas_reab_item_punto"),
        sa.CheckConstraint("stock_maximo >= stock_minimo", name="ck_reglas_reab_max_ge_min"),
    )
    op.create_index("idx_reglas_reabastecimiento_item", "reglas_reabastecimiento", ["item_inventario_id"])

    conn = op.get_bind()

    for item_ids, responsable in (
        (_ITEMS_POLLO, "POLLO"),
        (_ITEMS_DESECHABLE + _ITEMS_SALSA_BOTE, "DESECHABLE_SALSA"),
        (_ITEMS_VEGETAL, "VEGETAL"),
    ):
        conn.execute(
            sa.text("UPDATE items_inventario SET responsable_abastecimiento = :r WHERE id = ANY(:ids)"),
            {"r": responsable, "ids": item_ids},
        )

    reglas = sa.table(
        "reglas_reabastecimiento",
        sa.column("item_inventario_id", sa.Integer),
        sa.column("punto_venta_id", sa.Integer),
        sa.column("stock_minimo", sa.Numeric),
        sa.column("stock_maximo", sa.Numeric),
        sa.column("consumo_diario_base", sa.Numeric),
    )
    todas_las_reglas = _REGLAS_POLLO + _REGLAS_DESECHABLE + _REGLAS_SALSA_BOTE + _REGLAS_VEGETAL
    op.bulk_insert(
        reglas,
        [
            {
                "item_inventario_id": item_id,
                "punto_venta_id": _PUNTO_LOCAL_CENTRO,
                "stock_minimo": minimo,
                "stock_maximo": maximo,
                "consumo_diario_base": consumo_base,
            }
            for item_id, minimo, maximo, consumo_base in todas_las_reglas
        ],
    )


def downgrade() -> None:
    op.drop_index("idx_reglas_reabastecimiento_item", table_name="reglas_reabastecimiento")
    op.drop_table("reglas_reabastecimiento")

    op.drop_index("idx_pedidos_reab_responsable_estado", table_name="pedidos_reabastecimiento")
    op.drop_column("pedidos_reabastecimiento", "fecha_envio")
    op.drop_constraint("ck_pedidos_reab_responsable_tipo", "pedidos_reabastecimiento", type_="check")
    op.drop_column("pedidos_reabastecimiento", "responsable_tipo")

    op.drop_constraint("ck_items_inventario_responsable_abastecimiento", "items_inventario", type_="check")
    op.drop_column("items_inventario", "responsable_abastecimiento")
    # Nota: Postgres no soporta remover valores de un enum sin recrear el tipo -
    # GERENTE_CENTRAL queda en userrol tras el downgrade (mismo patrón que 002).
