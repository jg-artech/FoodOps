"""Módulo D: caja diaria, gastos, desperdicios, inventario diario, fondos de repartidor

Revision ID: 002_modulo_d_caja
Revises: 001_security_remediation
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "002_modulo_d_caja"
down_revision = "001_security_remediation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy's Enum(UserRol) column stores the member *name* (uppercase),
    # not its .value - so DB labels must be uppercase to match the Python enum.
    # 001 added 'gerente_general' (lowercase), which never matches; fixed here too.
    op.execute("ALTER TYPE userrol ADD VALUE IF NOT EXISTS 'GERENTE_GENERAL' AFTER 'ADMIN'")
    op.execute("ALTER TYPE userrol ADD VALUE IF NOT EXISTS 'RESP_TIENDA' AFTER 'GERENTE_PUNTO'")
    op.execute("ALTER TYPE userrol ADD VALUE IF NOT EXISTS 'REPARTIDOR' AFTER 'RESP_TIENDA'")

    op.create_table(
        "cajas_diarias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("fondo_inicial", sa.Numeric(10, 2), nullable=False),
        sa.Column("efectivo_esperado", sa.Numeric(10, 2)),
        sa.Column("efectivo_contado", sa.Numeric(10, 2)),
        sa.Column("descuadre", sa.Numeric(10, 2)),
        sa.Column("estado", sa.String(20), nullable=False, server_default="abierta"),
        sa.Column("abierta_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("cerrada_por", sa.Integer(), nullable=True),
        sa.Column("observacion_gerente", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("cerrada_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("punto_id", "fecha", name="uq_cajas_punto_fecha"),
    )

    op.create_table(
        "gastos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("caja_id", sa.Integer(), sa.ForeignKey("cajas_diarias.id"), nullable=False),
        sa.Column("punto_id", sa.Integer(), nullable=False),
        sa.Column("categoria", sa.String(40), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=False),
        sa.Column("monto", sa.Numeric(10, 2), nullable=False),
        sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.CheckConstraint("monto > 0", name="ck_gastos_monto_positivo"),
    )

    op.create_table(
        "items_inventario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), nullable=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("unidad", sa.String(20), nullable=False),
        sa.Column("producto_menu_id", sa.Integer(), nullable=True),
        sa.Column("orden_conteo", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "desperdicios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("producto_id", sa.Integer(), nullable=True),
        sa.Column("item_inventario_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=True),
        sa.Column("cantidad", sa.Numeric(8, 2), nullable=False),
        sa.Column("unidad", sa.String(20), nullable=False),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column("costo_estimado", sa.Numeric(10, 2), nullable=True),
        sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.CheckConstraint("cantidad > 0", name="ck_desperdicios_cantidad_positiva"),
    )

    op.create_table(
        "inventarios_diarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("caja_id", sa.Integer(), sa.ForeignKey("cajas_diarias.id"), nullable=False),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("momento", sa.String(20), nullable=False),
        sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("completado", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("punto_id", "fecha", "momento", name="uq_inv_diario_punto_fecha_momento"),
    )

    op.create_table(
        "inventario_detalle",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("inventario_id", sa.Integer(), sa.ForeignKey("inventarios_diarios.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items_inventario.id"), nullable=False),
        sa.Column("cantidad", sa.Numeric(10, 2), nullable=False),
        sa.UniqueConstraint("inventario_id", "item_id", name="uq_inv_detalle_inventario_item"),
        sa.CheckConstraint("cantidad >= 0", name="ck_inv_detalle_cantidad_no_negativa"),
    )

    op.create_table(
        "fondos_repartidor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("caja_id", sa.Integer(), sa.ForeignKey("cajas_diarias.id"), nullable=False),
        sa.Column("repartidor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("monto_entregado", sa.Numeric(10, 2), nullable=False),
        sa.Column("monto_liquidado", sa.Numeric(10, 2), nullable=True),
        sa.Column("diferencia", sa.Numeric(10, 2), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="entregado"),
        sa.Column("entregado_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("liquidado_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "transacciones_pedidos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("punto_id", sa.Integer(), sa.ForeignKey("puntos_venta.id"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("completado_por", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("completado_at", sa.DateTime(), nullable=True),
    )

    op.create_index("idx_cajas_punto_fecha", "cajas_diarias", ["punto_id", "fecha"])
    op.create_index("idx_gastos_caja", "gastos", ["caja_id"])
    op.create_index("idx_desperdicios_punto", "desperdicios", ["punto_id"])
    op.create_index("idx_inventario_diarios_caja", "inventarios_diarios", ["caja_id"])

    # Seed catálogo de items_inventario (punto_id=2, según hoja física de conteo)
    items_inventario = sa.table(
        "items_inventario",
        sa.column("punto_id", sa.Integer),
        sa.column("nombre", sa.String),
        sa.column("tipo", sa.String),
        sa.column("unidad", sa.String),
        sa.column("producto_menu_id", sa.Integer),
        sa.column("orden_conteo", sa.Integer),
        sa.column("activo", sa.Boolean),
    )
    op.bulk_insert(
        items_inventario,
        [
            {"punto_id": 2, "nombre": "Pollo Entero", "tipo": "vendible", "unidad": "unidad", "producto_menu_id": 1, "orden_conteo": 1, "activo": True},
            {"punto_id": 2, "nombre": "1/2 Pollo", "tipo": "vendible", "unidad": "unidad", "producto_menu_id": 2, "orden_conteo": 2, "activo": True},
            {"punto_id": 2, "nombre": "1/4 Pollo", "tipo": "vendible", "unidad": "unidad", "producto_menu_id": 3, "orden_conteo": 3, "activo": True},
            {"punto_id": 2, "nombre": "Costilla 1 Lb", "tipo": "vendible", "unidad": "lb", "producto_menu_id": 4, "orden_conteo": 4, "activo": True},
            {"punto_id": 2, "nombre": "Costilla 1/2 Lb", "tipo": "vendible", "unidad": "lb", "producto_menu_id": 5, "orden_conteo": 5, "activo": True},
            {"punto_id": 2, "nombre": "Pepsi 1.75L", "tipo": "vendible", "unidad": "unidad", "producto_menu_id": 6, "orden_conteo": 6, "activo": True},
            {"punto_id": 2, "nombre": "Pepsi Jumbo", "tipo": "vendible", "unidad": "unidad", "producto_menu_id": 7, "orden_conteo": 7, "activo": True},
            {"punto_id": 2, "nombre": "Plato Hondo Grande (PHG)", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 8, "activo": True},
            {"punto_id": 2, "nombre": "Plato Hondo Pequeño (PHP)", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 9, "activo": True},
            {"punto_id": 2, "nombre": "Vasito", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 10, "activo": True},
            {"punto_id": 2, "nombre": "Tapa Vasito", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 11, "activo": True},
            {"punto_id": 2, "nombre": "Bolsa 9x9", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 12, "activo": True},
            {"punto_id": 2, "nombre": "Bolsa 7x7", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 13, "activo": True},
            {"punto_id": 2, "nombre": "Bolsa Lisa", "tipo": "desechable", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 14, "activo": True},
            {"punto_id": 2, "nombre": "Arroz", "tipo": "insumo", "unidad": "lb", "producto_menu_id": None, "orden_conteo": 15, "activo": True},
            {"punto_id": 2, "nombre": "Frijol", "tipo": "insumo", "unidad": "lb", "producto_menu_id": None, "orden_conteo": 16, "activo": True},
            {"punto_id": 2, "nombre": "Coditos", "tipo": "insumo", "unidad": "bolita", "producto_menu_id": None, "orden_conteo": 17, "activo": True},
            {"punto_id": 2, "nombre": "Consomé", "tipo": "insumo", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 18, "activo": True},
            {"punto_id": 2, "nombre": "Barbacoa", "tipo": "insumo", "unidad": "pack", "producto_menu_id": None, "orden_conteo": 19, "activo": True},
            {"punto_id": 2, "nombre": "Mayonesa", "tipo": "insumo", "unidad": "bote", "producto_menu_id": None, "orden_conteo": 20, "activo": True},
            {"punto_id": 2, "nombre": "Salsa", "tipo": "insumo", "unidad": "bote", "producto_menu_id": None, "orden_conteo": 21, "activo": True},
            {"punto_id": 2, "nombre": "Queso", "tipo": "insumo", "unidad": "lata", "producto_menu_id": None, "orden_conteo": 22, "activo": True},
            {"punto_id": 2, "nombre": "Leche", "tipo": "insumo", "unidad": "litro", "producto_menu_id": None, "orden_conteo": 23, "activo": True},
            {"punto_id": 2, "nombre": "Tomate", "tipo": "insumo", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 24, "activo": True},
            {"punto_id": 2, "nombre": "Chirmol Verde", "tipo": "insumo", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 25, "activo": True},
            {"punto_id": 2, "nombre": "Chirmol Rojo", "tipo": "insumo", "unidad": "unidad", "producto_menu_id": None, "orden_conteo": 26, "activo": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("transacciones_pedidos")
    op.drop_table("fondos_repartidor")
    op.drop_table("inventario_detalle")
    op.drop_table("inventarios_diarios")
    op.drop_table("desperdicios")
    op.drop_table("items_inventario")
    op.drop_table("gastos")
    op.drop_table("cajas_diarias")
    # Note: PostgreSQL does not support removing enum values without recreating the type
