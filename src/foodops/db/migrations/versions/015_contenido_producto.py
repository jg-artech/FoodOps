"""Contenido del producto en la base de datos.

- productos_menu.contenido: String(500), nullable. Texto que muestran el POS,
  órdenes y cocina (hasta ahora vivía solo en localStorage, desde
  foodops-web/src/data/menu.js). Mismo límite que la API.
- Datos, en este orden y solo donde contenido IS NULL:
  1. Copia descripcion a contenido, salvo cuando la descripción es igual al
     nombre (sin importar mayúsculas ni espacios): esas solo repetían el nombre.
  2. Carga los contenidos por defecto de menu.js usando el nombre del
     producto como clave. "Combo Costilla" recibe el de "Combo Costilla
     Familiar" de menu.js. Mega Combo y 1/4 Pollo no tienen equivalente y
     quedan vacíos. "Combo Familiar" no está en el mapa: usa su descripcion.
- descripcion NO se elimina aquí. Va en una migración posterior, cuando se
  verifique que nada la lee.

El downgrade elimina la columna contenido (descripcion no se tocó, así que
no hay nada que restaurar).

Revision ID: 015_contenido_producto
Revises: 014_cargo_entrega
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "015_contenido_producto"
down_revision = "014_cargo_entrega"
branch_labels = None
depends_on = None

# Nombre del producto en la base -> contenido por defecto (texto de menu.js).
CONTENIDOS_POR_DEFECTO = {
    "Super Combo": (
        "1 Pollo Entero, 1 Lb Costilla, 3 guarniciones, 8 cebollines, "
        "2 jalapeños, 1.75L Pepsi"
    ),
    # En menu.js se llama "Combo Costilla Familiar".
    "Combo Costilla": (
        "3 Lb costillas, 3 guarniciones, 10 cebollín, 4 jalapeños, "
        "1 chirmol, 1.75L Pepsi"
    ),
}


def upgrade() -> None:
    op.add_column(
        "productos_menu", sa.Column("contenido", sa.String(500), nullable=True)
    )

    op.execute(
        """
        UPDATE productos_menu
           SET contenido = descripcion
         WHERE contenido IS NULL
           AND descripcion IS NOT NULL
           AND btrim(descripcion) <> ''
           AND lower(regexp_replace(descripcion, '\\s', '', 'g'))
               <> lower(regexp_replace(nombre, '\\s', '', 'g'))
        """
    )

    actualizar = sa.text(
        "UPDATE productos_menu SET contenido = :contenido "
        "WHERE contenido IS NULL AND nombre = :nombre"
    )
    conn = op.get_bind()
    for nombre, contenido in CONTENIDOS_POR_DEFECTO.items():
        conn.execute(actualizar, {"nombre": nombre, "contenido": contenido})


def downgrade() -> None:
    op.drop_column("productos_menu", "contenido")
