"""Datos de facturación por orden (fase 1: solo captura, no se emiten facturas).

- datos_facturacion: a lo sumo una fila por orden (orden_id UNIQUE). La FK
  usa ON DELETE RESTRICT: una orden con datos fiscales no se puede borrar.
- Las órdenes existentes no reciben fila: sin fila se trata como
  requiere_factura = false. No se tocan datos históricos.
- factura_generada solo marca que el cobrador ya hizo la factura (manual);
  no hay número, XML ni PDF en esta fase.

Revision ID: 013_datos_facturacion
Revises: 012_impresion_agente
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "013_datos_facturacion"
down_revision = "012_impresion_agente"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datos_facturacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "orden_id",
            sa.Integer(),
            sa.ForeignKey("ordenes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requiere_factura", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nit", sa.String(20), nullable=True),
        sa.Column("nombre_fiscal", sa.String(200), nullable=True),
        sa.Column("direccion_fiscal", sa.String(255), nullable=True),
        sa.Column("factura_generada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("factura_generada_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("factura_generada_at", sa.DateTime(), nullable=True),
        sa.Column("capturado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("capturado_at", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("actualizado_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("orden_id", name="uq_datos_facturacion_orden"),
        # Una factura marcada como generada siempre requiere factura y
        # registra quién y cuándo la marcó.
        sa.CheckConstraint(
            "NOT factura_generada OR (requiere_factura "
            "AND factura_generada_por IS NOT NULL AND factura_generada_at IS NOT NULL)",
            name="ck_datos_facturacion_generada",
        ),
    )


def downgrade() -> None:
    op.drop_table("datos_facturacion")
