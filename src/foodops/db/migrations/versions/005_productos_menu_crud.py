"""Habilita CRUD de productos_menu desde ConfigView: agrega descripcion y convierte
id en autoincremental (antes solo tenía los 14 ids sembrados a mano en la migración 004,
sin secuencia - cualquier INSERT sin id explícito habría fallado).

Revision ID: 005_productos_menu_crud
Revises: 004_stock_reabastecimiento
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "005_productos_menu_crud"
down_revision = "004_stock_reabastecimiento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("productos_menu", sa.Column("descripcion", sa.String(200), nullable=True))
    op.add_column(
        "productos_menu",
        sa.Column("unidad", sa.String(20), nullable=False, server_default="unidad"),
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS productos_menu_id_seq OWNED BY productos_menu.id")
    op.execute("SELECT setval('productos_menu_id_seq', COALESCE((SELECT MAX(id) FROM productos_menu), 1))")
    op.execute("ALTER TABLE productos_menu ALTER COLUMN id SET DEFAULT nextval('productos_menu_id_seq')")


def downgrade() -> None:
    op.execute("ALTER TABLE productos_menu ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS productos_menu_id_seq")
    op.drop_column("productos_menu", "unidad")
    op.drop_column("productos_menu", "descripcion")
