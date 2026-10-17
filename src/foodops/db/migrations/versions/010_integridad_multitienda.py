"""Integridad multitienda: FK e índice de tienda, tienda obligatoria por rol,
número de orden único por tienda y catálogo de inventario global.

Ver docs/AUDITORIA_MULTITIENDA.md (R3, R8, R9).

Nota sobre el enum de rol: PostgreSQL guarda el NOMBRE del miembro
('GERENTE_GENERAL'), no su valor ('gerente_general'), que es lo que viaja en
el JWT. El CHECK compara contra los nombres.

Revision ID: 010_integridad_multitienda
Revises: 009_indices_performance
Create Date: 2026-10-17
"""
from alembic import op

revision = "010_integridad_multitienda"
down_revision = "009_indices_performance"
branch_labels = None
depends_on = None

# Roles que pueden existir sin tienda asignada (ven todas o ninguna en concreto).
_ROLES_SIN_TIENDA = "('ADMIN', 'GERENTE_GENERAL', 'GERENTE_CENTRAL')"


def upgrade() -> None:
    # --- 1. gastos.punto_id era un Integer suelto, sin FK -------------------
    op.execute(
        """
        ALTER TABLE gastos
        ADD CONSTRAINT fk_gastos_punto_id
        FOREIGN KEY (punto_id) REFERENCES puntos_venta(id)
        """
    )

    # --- 2. índice: todo filtra por tienda ---------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_punto_id ON usuarios(punto_id)")

    # --- 3. un rol de tienda no puede quedarse sin tienda ------------------
    # El login ya lo rechaza; esto impide crear el usuario roto de entrada.
    op.execute(
        f"""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_tienda_segun_rol
        CHECK (punto_id IS NOT NULL OR rol::text IN {_ROLES_SIN_TIENDA})
        """
    )

    # --- 4. numero_orden único por tienda ----------------------------------
    # El formato era ORD-{YYYYMMDDHHMMSS}: dos tiendas vendiendo en el mismo
    # segundo generaban el mismo número, que es el que se imprime en el ticket
    # y se usa en cocina. El código pasa a ORD-{punto}-{timestamp}; los
    # números viejos se quedan como están, por eso la unicidad es por tienda
    # y no global.
    op.execute(
        """
        ALTER TABLE ordenes
        ADD CONSTRAINT uq_ordenes_punto_numero UNIQUE (punto_id, numero_orden)
        """
    )

    # --- 5. items_inventario es un catálogo de empresa, no de tienda -------
    # Estaba a medias (unos items con punto_id, otros NULL) y ningún endpoint
    # filtraba por esa columna. Las recetas de producto_componentes apuntan a
    # items de ambos grupos, así que tratarlo como catálogo global es lo único
    # que no rompe las recetas en las tiendas que no son Centro. El stock por
    # tienda no sale de aquí: sale de inventarios_diarios, transacciones_venta
    # y pedidos_reabastecimiento, que sí llevan punto_id.
    op.execute("UPDATE items_inventario SET punto_id = NULL WHERE punto_id IS NOT NULL")


def downgrade() -> None:
    # El punto_id original de items_inventario no se restaura: era un dato
    # accidental (la tienda de quien creó el item), no información de negocio.
    op.execute("ALTER TABLE ordenes DROP CONSTRAINT IF EXISTS uq_ordenes_punto_numero")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS ck_usuarios_tienda_segun_rol")
    op.execute("DROP INDEX IF EXISTS idx_usuarios_punto_id")
    op.execute("ALTER TABLE gastos DROP CONSTRAINT IF EXISTS fk_gastos_punto_id")
