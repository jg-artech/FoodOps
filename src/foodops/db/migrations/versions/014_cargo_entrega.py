"""Cargo de entrega en órdenes a domicilio y tope por tienda.

- puntos_venta.tope_cargo_entrega: monto máximo del cargo sin autorización
  de un responsable. Numeric(10,2), 200.00 por defecto (las tiendas
  existentes quedan con 200.00).
- orden_items.tipo: 'producto' | 'entrega'. String + CHECK, misma convención
  que ordenes.estado_cobro (011) y trabajos_impresion.tipo (012). Las filas
  existentes quedan como 'producto'. Índice único parcial: a lo sumo un
  cargo de entrega por orden.
- autorizaciones_cargo_usadas: jti de cada token de autorización ya usado.
  La PK sobre jti es la que impide reutilizar un token (uso único).

Revision ID: 014_cargo_entrega
Revises: 013_datos_facturacion
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "014_cargo_entrega"
down_revision = "013_datos_facturacion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "puntos_venta",
        sa.Column(
            "tope_cargo_entrega",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("200.00"),
        ),
    )
    op.create_check_constraint(
        "ck_puntos_venta_tope_cargo_entrega", "puntos_venta", "tope_cargo_entrega >= 0"
    )

    op.add_column(
        "orden_items",
        sa.Column("tipo", sa.String(20), nullable=False, server_default="producto"),
    )
    op.create_check_constraint(
        "ck_orden_items_tipo", "orden_items", "tipo IN ('producto', 'entrega')"
    )
    op.create_index(
        "ux_orden_items_entrega_por_orden",
        "orden_items",
        ["orden_id"],
        unique=True,
        postgresql_where=sa.text("tipo = 'entrega'"),
    )

    op.create_table(
        "autorizaciones_cargo_usadas",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id"), nullable=False),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("autorizado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("usado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("monto", sa.Numeric(10, 2), nullable=False),
        sa.Column("usado_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("autorizaciones_cargo_usadas")
    op.drop_index("ux_orden_items_entrega_por_orden", table_name="orden_items")
    op.drop_constraint("ck_orden_items_tipo", "orden_items", type_="check")
    op.drop_column("orden_items", "tipo")
    op.drop_constraint("ck_puntos_venta_tope_cargo_entrega", "puntos_venta", type_="check")
    op.drop_column("puntos_venta", "tope_cargo_entrega")
