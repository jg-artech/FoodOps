"""Personal de cocina por tienda y responsable de preparar cada orden.

- personal_cocina: catálogo por tienda (punto_id), administrable sin borrado
  físico (activo = false para desactivar, por la rotación). Sin vínculo con
  usuarios: decisión del 2026-11-25, la cocina puede usar un usuario
  compartido. Índice por (punto_id, activo): el selector de cocina lista el
  personal activo de una tienda.
- ordenes.responsable_cocina_id: FK a personal_cocina, nullable. La orden
  guarda el id, no el nombre, para que un cambio de nombre no altere los
  reportes.
- ordenes.en_preparacion_at: hora de la primera asignación de responsable.
- ordenes.exige_responsable_cocina: las órdenes existentes quedan en false
  (se cierran sin responsable, decisión del 2026-11-25); las nuevas nacen en
  true y no pasan a listo ni a entregado sin responsable.

Sin datos históricos: las órdenes existentes quedan con responsable nulo.

Revision ID: 016_personal_cocina
Revises: 015_contenido_producto
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "016_personal_cocina"
down_revision = "015_contenido_producto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_cocina",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_personal_cocina_punto_activo", "personal_cocina", ["punto_id", "activo"])

    op.add_column(
        "ordenes",
        sa.Column(
            "responsable_cocina_id",
            sa.Integer(),
            sa.ForeignKey("personal_cocina.id", name="fk_ordenes_responsable_cocina"),
            nullable=True,
        ),
    )
    op.add_column("ordenes", sa.Column("en_preparacion_at", sa.DateTime(), nullable=True))
    # Existentes: false. Las nuevas reciben true desde el modelo (default=True).
    op.add_column(
        "ordenes",
        sa.Column(
            "exige_responsable_cocina",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("ordenes", "exige_responsable_cocina")
    op.drop_column("ordenes", "en_preparacion_at")
    op.drop_constraint("fk_ordenes_responsable_cocina", "ordenes", type_="foreignkey")
    op.drop_column("ordenes", "responsable_cocina_id")
    op.drop_index("ix_personal_cocina_punto_activo", table_name="personal_cocina")
    op.drop_table("personal_cocina")
