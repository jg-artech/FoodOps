"""Categorías del menú en la base, con posición.

Antes las categorías vivían en el localStorage de cada navegador: una
categoría creada en una computadora no existía en la tablet del POS. Ahora:

- categorias_menu: clave (la que guarda productos_menu.categoria, no cambia),
  nombre, emoji, posicion (orden en Nueva orden y Configuración) y activo.
  Sin borrado físico.
- Carga inicial con el orden pedido el 2026-11-26: Combos, Costillas, Pollos,
  Guarniciones, Bebidas y Extras, activas.
- Cualquier otra categoría que ya usen los productos (p. ej.
  pollo_por_piezas, las piezas del modal) se crea inactiva al final: hoy no
  aparece en el POS y así sigue hasta que gerencia la active.

Revision ID: 017_categorias_menu
Revises: 016_personal_cocina
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa

revision = "017_categorias_menu"
down_revision = "016_personal_cocina"
branch_labels = None
depends_on = None

INICIALES = [
    ("combos", "Combos", "🥘"),
    ("costillas", "Costillas", "🥓"),
    ("pollos", "Pollos", "🍗"),
    ("guarniciones", "Guarniciones", "🥔"),
    ("bebidas", "Bebidas", "🥤"),
    ("extras", "Extras", "➕"),
]


def upgrade():
    tabla = op.create_table(
        "categorias_menu",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(50), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=True),
        sa.Column("posicion", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("clave", name="uq_categorias_menu_clave"),
    )

    filas = [
        {"clave": clave, "nombre": nombre, "emoji": emoji, "posicion": i, "activo": True}
        for i, (clave, nombre, emoji) in enumerate(INICIALES, start=1)
    ]
    conocidas = {f["clave"] for f in filas}
    otras = op.get_bind().execute(
        sa.text("SELECT DISTINCT categoria FROM productos_menu ORDER BY categoria")
    ).scalars().all()
    for clave in otras:
        if clave and clave not in conocidas:
            filas.append({
                "clave": clave,
                "nombre": clave.replace("_", " ").capitalize()[:50],
                "emoji": None,
                "posicion": len(filas) + 1,
                "activo": False,
            })
    op.bulk_insert(tabla, filas)


def downgrade():
    op.drop_table("categorias_menu")
