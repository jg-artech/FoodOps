"""Security remediation: rate limiting columns, tomada_por, audit_log, GERENTE_GENERAL role

Revision ID: 001_security_remediation
Revises:
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "001_security_remediation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add GERENTE_GENERAL to the userrol enum (PostgreSQL-specific)
    op.execute("ALTER TYPE userrol ADD VALUE IF NOT EXISTS 'gerente_general' AFTER 'admin'")

    # Add rate-limiting columns to usuarios
    op.add_column("usuarios", sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usuarios", sa.Column("bloqueado_hasta", sa.DateTime(), nullable=True))

    # Add tomada_por to ordenes
    op.add_column(
        "ordenes",
        sa.Column("tomada_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
    )

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("punto_id", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(60), nullable=False),
        sa.Column("entidad", sa.String(40), nullable=False),
        sa.Column("entidad_id", sa.String(40), nullable=True),
        sa.Column("detalle", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_column("ordenes", "tomada_por")
    op.drop_column("usuarios", "bloqueado_hasta")
    op.drop_column("usuarios", "intentos_fallidos")
    # Note: PostgreSQL does not support removing enum values without recreating the type
