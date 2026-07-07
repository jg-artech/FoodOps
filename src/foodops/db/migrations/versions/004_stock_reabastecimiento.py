"""Etapa 2.5: stock en vivo + reabastecimiento (transaccion_componentes, productos_menu,
producto_componentes, pedidos_reabastecimiento)

Revision ID: 004_stock_reabastecimiento
Revises: 003_transacciones_venta
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "004_stock_reabastecimiento"
down_revision = "003_transacciones_venta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # productos_menu: no existía tabla canónica de productos - el menú vive solo en
    # localStorage del frontend (data/menu.js). Se crea aquí para poder enlazar recetas
    # (producto_componentes); se siembra con el catálogo por defecto de MENU_ITEMS.
    # Si un usuario edita el menú vía ConfigView (solo localStorage), productos nuevos
    # o renombrados no tendrán receta hasta que se agregue manualmente en esta tabla.
    op.create_table(
        "productos_menu",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("precio", sa.Numeric(10, 2), nullable=False),
        sa.Column("categoria", sa.String(30), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="individual"),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "producto_componentes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("producto_menu_id", sa.Integer(), sa.ForeignKey("productos_menu.id"), nullable=False),
        sa.Column("item_inventario_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=False),
        sa.Column("cantidad", sa.Numeric(8, 2), nullable=False),
        sa.Column("elegible", sa.Boolean(), server_default=sa.text("false")),
    )

    op.create_table(
        "transaccion_componentes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("transaccion_id", sa.Integer(), sa.ForeignKey("transacciones_venta.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_inventario_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=False),
        sa.Column("cantidad", sa.Numeric(8, 2), nullable=False),
        sa.Column("tipo_origen", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.CheckConstraint("cantidad > 0", name="ck_transaccion_componentes_cantidad_positiva"),
    )
    op.create_index("idx_transaccion_componentes_transaccion", "transaccion_componentes", ["transaccion_id"])
    op.create_index("idx_transaccion_componentes_item", "transaccion_componentes", ["item_inventario_id"])

    op.create_table(
        "pedidos_reabastecimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("total_estimado", sa.Numeric(10, 2), nullable=True),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("confirmado_por", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("confirmado_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_pedidos_punto", "pedidos_reabastecimiento", ["punto_id"])
    op.create_index("idx_pedidos_estado", "pedidos_reabastecimiento", ["estado"])

    op.create_table(
        "pedido_reabastecimiento_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pedido_id", sa.Integer(), sa.ForeignKey("pedidos_reabastecimiento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_inventario_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=False),
        sa.Column("cantidad_solicitada", sa.Numeric(8, 2), nullable=False),
        sa.Column("cantidad_recibida", sa.Numeric(8, 2), nullable=True),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=True),
        sa.Column("costo_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("razon_solicitud", sa.String(100), nullable=True),
    )

    # --- Seed productos_menu desde el catálogo REAL de foodops-web/src/data/menu.js ---
    # (la spec original traía ids 1-23 ficticios que no existen en el menú real ni en
    # items_inventario; se reconstruye aquí contra el catálogo que el POS usa de verdad)
    productos_menu = sa.table(
        "productos_menu",
        sa.column("id", sa.Integer),
        sa.column("nombre", sa.String),
        sa.column("precio", sa.Numeric),
        sa.column("categoria", sa.String),
        sa.column("tipo", sa.String),
    )
    op.bulk_insert(
        productos_menu,
        [
            {"id": 1, "nombre": "Pollo Entero", "precio": 75, "categoria": "pollos", "tipo": "individual"},
            {"id": 2, "nombre": "½ Pollo", "precio": 45, "categoria": "pollos", "tipo": "individual"},
            {"id": 3, "nombre": "¼ Pollo", "precio": 25, "categoria": "pollos", "tipo": "individual"},
            {"id": 4, "nombre": "1 Lb Costilla", "precio": 50, "categoria": "costillas", "tipo": "individual"},
            {"id": 5, "nombre": "½ Lb Costilla", "precio": 25, "categoria": "costillas", "tipo": "individual"},
            {"id": 6, "nombre": "Combo Familiar", "precio": 90, "categoria": "combos", "tipo": "combo"},
            {"id": 7, "nombre": "Super Combo", "precio": 130, "categoria": "combos", "tipo": "combo"},
            {"id": 8, "nombre": "Combo Costilla Familiar", "precio": 140, "categoria": "combos", "tipo": "combo"},
            {"id": 9, "nombre": "Papa al vapor", "precio": 5, "categoria": "guarniciones", "tipo": "individual"},
            {"id": 10, "nombre": "Arroz con verdura", "precio": 5, "categoria": "guarniciones", "tipo": "individual"},
            {"id": 11, "nombre": "Ensalada Rusa", "precio": 5, "categoria": "guarniciones", "tipo": "individual"},
            {"id": 12, "nombre": "Papas con queso", "precio": 10, "categoria": "guarniciones", "tipo": "individual"},
            {"id": 13, "nombre": "Coditos", "precio": 5, "categoria": "guarniciones", "tipo": "individual"},
            {"id": 14, "nombre": "Porción Extra", "precio": 5, "categoria": "extras", "tipo": "individual"},
        ],
    )

    # --- Seed producto_componentes: solo recetas donde hay un item_inventario real e
    # inequívoco. Guarniciones/condimentos sin item físico en la hoja de conteo (papa,
    # lechuga, cebollín, jalapeño) quedan sin receta a propósito - registrarlos habría
    # sido una adivinanza, no un dato real. Ningún componente se marca elegible=true
    # porque el POS actual no captura qué guarnición específica eligió el cliente dentro
    # de un combo (los combos se venden como una sola línea de carrito).
    producto_componentes = sa.table(
        "producto_componentes",
        sa.column("producto_menu_id", sa.Integer),
        sa.column("item_inventario_id", sa.Integer),
        sa.column("cantidad", sa.Numeric),
        sa.column("elegible", sa.Boolean),
    )
    op.bulk_insert(
        producto_componentes,
        [
            # Pollo Entero -> items_inventario#1 Pollo Entero
            {"producto_menu_id": 1, "item_inventario_id": 1, "cantidad": 1, "elegible": False},
            # 1/2 Pollo -> items_inventario#2
            {"producto_menu_id": 2, "item_inventario_id": 2, "cantidad": 1, "elegible": False},
            # 1/4 Pollo -> items_inventario#3
            {"producto_menu_id": 3, "item_inventario_id": 3, "cantidad": 1, "elegible": False},
            # 1 Lb Costilla -> items_inventario#4
            {"producto_menu_id": 4, "item_inventario_id": 4, "cantidad": 1, "elegible": False},
            # 1/2 Lb Costilla -> items_inventario#5
            {"producto_menu_id": 5, "item_inventario_id": 5, "cantidad": 1, "elegible": False},
            # Combo Familiar: "1 pollo entero, 3 guarniciones, 5 cebollines, 1 jalapeño"
            # -> solo el pollo entero es rastreable; guarniciones/cebollín/jalapeño sin item
            {"producto_menu_id": 6, "item_inventario_id": 1, "cantidad": 1, "elegible": False},
            # Super Combo: "1 Pollo Entero, 1 Lb Costilla, ..., 1.75L Pepsi"
            {"producto_menu_id": 7, "item_inventario_id": 1, "cantidad": 1, "elegible": False},
            {"producto_menu_id": 7, "item_inventario_id": 4, "cantidad": 1, "elegible": False},
            {"producto_menu_id": 7, "item_inventario_id": 6, "cantidad": 1, "elegible": False},
            # Combo Costilla Familiar: "3 Lb costillas, ..., 1.75L Pepsi"
            {"producto_menu_id": 8, "item_inventario_id": 4, "cantidad": 3, "elegible": False},
            {"producto_menu_id": 8, "item_inventario_id": 6, "cantidad": 1, "elegible": False},
            # Arroz con verdura -> items_inventario#15 Arroz
            {"producto_menu_id": 10, "item_inventario_id": 15, "cantidad": 1, "elegible": False},
            # Coditos (guarnición) -> items_inventario#17 Coditos
            {"producto_menu_id": 13, "item_inventario_id": 17, "cantidad": 1, "elegible": False},
            # Papa al vapor (9), Ensalada Rusa (11), Papas con queso (12), Porción Extra (14):
            # sin receta - no hay item_inventario equivalente en la hoja de conteo actual
        ],
    )


def downgrade() -> None:
    op.drop_table("pedido_reabastecimiento_items")
    op.drop_table("pedidos_reabastecimiento")
    op.drop_table("transaccion_componentes")
    op.drop_table("producto_componentes")
    op.drop_table("productos_menu")
