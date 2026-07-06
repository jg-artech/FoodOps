"""Crea transacciones_venta (definida en models.py pero nunca migrada), requerida por
crear_transaccion/reporte_rentabilidad existentes y por el cálculo de efectivo_esperado del Módulo D

Revision ID: 003_transacciones_venta
Revises: 002_modulo_d_caja
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "003_transacciones_venta"
down_revision = "002_modulo_d_caja"
branch_labels = None
depends_on = None

# matches models.py TipoVenta: SQLAlchemy Enum columns store the member *name* (uppercase)
_tipo_venta_enum = sa.Enum("INDIVIDUAL", "COMBO", "INICIATIVA", name="tipoventa")


def upgrade() -> None:
    op.create_table(
        "transacciones_venta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id"), nullable=True),
        sa.Column("tipo_venta", _tipo_venta_enum, nullable=False, server_default="INDIVIDUAL"),
        sa.Column("nombre_iniciativa", sa.String(100), nullable=True),
        sa.Column("cliente_nombre", sa.String(100), nullable=True),
        sa.Column("cliente_telefono", sa.String(20), nullable=True),
        sa.Column("cliente_direccion", sa.Text(), nullable=True),
        sa.Column("tipo_cliente", sa.String(20), nullable=False, server_default="para_llevar"),
        sa.Column("precio_venta", sa.Float(), nullable=False),
        sa.Column("costo_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margen_bruto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margen_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metodo_pago", sa.String(50), nullable=True),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("requerimientos_especiales", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(50), nullable=False, server_default="completada"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_transacciones_venta_punto_created", "transacciones_venta", ["punto_id", "created_at"])


def downgrade() -> None:
    op.drop_table("transacciones_venta")
    _tipo_venta_enum.drop(op.get_bind(), checkfirst=True)
