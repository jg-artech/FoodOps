"""Índices de performance en reglas_reabastecimiento y audit_log.

Parte de la auditoría de performance del CRUD de puntos_venta: de los 6
índices pedidos, 3 ya existían con otro nombre (idx_transaccion_componentes_
transaccion/item, idx_reglas_reabastecimiento_item) - se omiten para no
duplicar índices redundantes sobre las mismas columnas. Solo se agregan los
3 que realmente faltaban.

Revision ID: 009_indices_performance
Revises: 008_grupo_elegible_min_max
Create Date: 2026-08-17
"""
from alembic import op

revision = "009_indices_performance"
down_revision = "008_grupo_elegible_min_max"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_reglas_punto_id ON reglas_reabastecimiento(punto_venta_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_usuario_id ON audit_log(usuario_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_log_created_at")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_usuario_id")
    op.execute("DROP INDEX IF EXISTS idx_reglas_punto_id")
