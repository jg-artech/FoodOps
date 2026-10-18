"""Estado de cobro en efectivo: eje independiente del estado de cocina.

Ver docs/AUDITORIA_COBRO_EFECTIVO.md. `ordenes.estado` sigue siendo
exclusivamente el estado de cocina (pendiente/preparando/listo/entregado/
cancelado) - está enganchado por exact-match en 4+ vistas del frontend
(KitchenView, OrdersListView, POSMainView) y mezclarlo con el flujo de cobro
le habría impedido a cocina ver las órdenes en efectivo hasta que alguien
confirmara el dinero, algo completamente ajeno a si ya se coció el pedido.

`estado_cobro` es un String simple, no un Enum nativo de Postgres, igual que
`cajas_diarias.estado` / `transacciones_venta.estado` /
`pedidos_reabastecimiento.estado` en el resto del proyecto - evita el
ALTER TYPE ADD VALUE que complicaría agregar un estado nuevo más adelante
(a diferencia de `ordenes.estado`, que sí es un Enum nativo desde el
origen del proyecto).

Las órdenes existentes se backfillean a "cobrada" (server_default): ya
fueron cobradas en la práctica, marcarlas retroactivamente como pendientes
solo bloquearía cierres de caja por datos históricos sin ningún beneficio.

Revision ID: 011_estado_cobro
Revises: 010_integridad_multitienda
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "011_estado_cobro"
down_revision = "010_integridad_multitienda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordenes",
        sa.Column("estado_cobro", sa.String(20), nullable=False, server_default="cobrada"),
    )
    op.add_column("ordenes", sa.Column("monto_recibido", sa.Float(), nullable=True))
    op.add_column("ordenes", sa.Column("vuelto_entregado", sa.Float(), nullable=True))
    op.add_column(
        "ordenes",
        sa.Column("confirmado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
    )
    op.add_column("ordenes", sa.Column("confirmado_at", sa.DateTime(), nullable=True))

    op.create_check_constraint(
        "ck_ordenes_estado_cobro_valido",
        "ordenes",
        "estado_cobro IN ('pendiente_recibir', 'cobrada')",
    )
    # Para el filtro de cerrar_caja (¿hay pendientes en este punto?) y el
    # join de _calcular_efectivo_esperado.
    op.create_index("ix_ordenes_punto_estado_cobro", "ordenes", ["punto_id", "estado_cobro"])


def downgrade() -> None:
    op.drop_index("ix_ordenes_punto_estado_cobro", table_name="ordenes")
    op.drop_constraint("ck_ordenes_estado_cobro_valido", "ordenes", type_="check")
    op.drop_column("ordenes", "confirmado_at")
    op.drop_column("ordenes", "confirmado_por")
    op.drop_column("ordenes", "vuelto_entregado")
    op.drop_column("ordenes", "monto_recibido")
    op.drop_column("ordenes", "estado_cobro")
