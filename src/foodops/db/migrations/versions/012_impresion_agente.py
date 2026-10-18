"""Impresión por agente de tienda + apertura de cajón.

Ver docs/DISENO_IMPRESION.md §3, §5 y §6.

- puntos_venta: impresora_ip, impresora_puerto (9100), impresora_activa
  (False), cajon_activo (False). Todas las tiendas quedan desactivadas hasta
  que se confirme cada impresora.
- trabajos_impresion: cola de trabajos TICKET / ABRIR_CAJON que el agente
  recoge por polling. tipo/estado son String + CHECK (misma convención que
  ordenes.estado_cobro en la 011). Índice único parcial: a lo sumo un
  ABRIR_CAJON por orden.
- tokens_agente: token de cada agente (solo sha256), con historial y a lo
  sumo un token activo por tienda (índice único parcial). El heartbeat
  (ultima_conexion_at) vive aquí, no en puntos_venta.

Revision ID: 012_impresion_agente
Revises: 011_estado_cobro
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "012_impresion_agente"
down_revision = "011_estado_cobro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("puntos_venta", sa.Column("impresora_ip", sa.String(45), nullable=True))
    op.add_column(
        "puntos_venta",
        sa.Column("impresora_puerto", sa.Integer(), nullable=False, server_default="9100"),
    )
    op.add_column(
        "puntos_venta",
        sa.Column("impresora_activa", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "puntos_venta",
        sa.Column("cajon_activo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "trabajos_impresion",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("solicitado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column("orden_id", sa.Integer(), sa.ForeignKey("ordenes.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("tomado_at", sa.DateTime(), nullable=True),
        sa.Column("completado_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("tipo IN ('ticket', 'abrir_cajon')", name="ck_trabajos_impresion_tipo"),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'imprimiendo', 'ok', 'error')",
            name="ck_trabajos_impresion_estado",
        ),
    )
    op.create_index(
        "ix_trabajos_impresion_punto_estado", "trabajos_impresion", ["punto_id", "estado"]
    )
    op.create_index("ix_trabajos_impresion_orden", "trabajos_impresion", ["orden_id"])
    op.create_index(
        "ux_trabajos_impresion_cajon_por_orden",
        "trabajos_impresion",
        ["orden_id"],
        unique=True,
        postgresql_where=sa.text("tipo = 'abrir_cajon'"),
    )

    op.create_table(
        "tokens_agente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("revocado_at", sa.DateTime(), nullable=True),
        sa.Column("ultima_conexion_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tokens_agente_punto_activo", "tokens_agente", ["punto_id", "activo"])
    op.create_index(
        "ux_tokens_agente_punto_unico_activo",
        "tokens_agente",
        ["punto_id"],
        unique=True,
        postgresql_where=sa.text("activo = true"),
    )


def downgrade() -> None:
    op.drop_index("ux_tokens_agente_punto_unico_activo", table_name="tokens_agente")
    op.drop_index("ix_tokens_agente_punto_activo", table_name="tokens_agente")
    op.drop_table("tokens_agente")

    op.drop_index("ux_trabajos_impresion_cajon_por_orden", table_name="trabajos_impresion")
    op.drop_index("ix_trabajos_impresion_orden", table_name="trabajos_impresion")
    op.drop_index("ix_trabajos_impresion_punto_estado", table_name="trabajos_impresion")
    op.drop_table("trabajos_impresion")

    op.drop_column("puntos_venta", "cajon_activo")
    op.drop_column("puntos_venta", "impresora_activa")
    op.drop_column("puntos_venta", "impresora_puerto")
    op.drop_column("puntos_venta", "impresora_ip")
