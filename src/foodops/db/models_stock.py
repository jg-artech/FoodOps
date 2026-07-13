"""Modelos SQLAlchemy para Etapa 2.5: stock en vivo, recetas y reabastecimiento"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from foodops.db.models import Base


class ProductoMenu(Base):
    __tablename__ = "productos_menu"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    precio = Column(Numeric(10, 2), nullable=False)
    categoria = Column(String(30), nullable=False)
    tipo = Column(String(20), nullable=False, default="individual")
    unidad = Column(String(20), nullable=False, default="unidad")
    descripcion = Column(String(200), nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductoComponente(Base):
    __tablename__ = "producto_componentes"

    id = Column(Integer, primary_key=True)
    producto_menu_id = Column(Integer, ForeignKey("productos_menu.id"), nullable=False)
    item_inventario_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=False)
    cantidad = Column(Numeric(8, 2), nullable=False)
    elegible = Column(Boolean, default=False)
    # NULL = componente fijo. Un entero agrupa componentes del mismo producto que
    # forman un "elige N" independiente (p.ej. Pieza vs Guarnición en ¼ Pollo).
    grupo_elegible = Column(Integer, nullable=True)
    nombre_grupo = Column(String(100), nullable=True)
    # Cuántas opciones del grupo debe/puede elegir el cliente. 1/1 = radio (default,
    # compatible con grupos existentes). Todas las filas de un mismo grupo_elegible
    # deben compartir el mismo valor (ver _validar_grupos en router_config.py).
    cantidad_elegible_minima = Column(Integer, nullable=False, default=1)
    cantidad_elegible_maxima = Column(Integer, nullable=False, default=1)


class TransaccionComponente(Base):
    __tablename__ = "transaccion_componentes"

    id = Column(BigInteger, primary_key=True)
    transaccion_id = Column(Integer, ForeignKey("transacciones_venta.id", ondelete="CASCADE"), nullable=False)
    item_inventario_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=False)
    cantidad = Column(Numeric(8, 2), nullable=False)
    tipo_origen = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_transaccion_componentes_cantidad_positiva"),)


class PedidoReabastecimiento(Base):
    __tablename__ = "pedidos_reabastecimiento"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    tipo = Column(String(20), nullable=False)
    estado = Column(String(20), nullable=False, default="pendiente")
    total_estimado = Column(Numeric(10, 2), nullable=True)
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    confirmado_por = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmado_at = Column(DateTime, nullable=True)
    # Módulo D (abastecimiento inteligente): NULL = pedido "clásico" iniciado por
    # la tienda (flujo previo, sin cambios). Si viene de una sugerencia generada
    # por un responsable central (POLLO/VEGETAL/DESECHABLE_SALSA), se etiqueta
    # aquí en vez de crear una tabla pedidos_abastecimiento paralela - es el
    # mismo pedido, solo con más contexto de origen.
    responsable_tipo = Column(String(30), nullable=True)
    fecha_envio = Column(Date, nullable=True)


class PedidoReabastecimientoItem(Base):
    __tablename__ = "pedido_reabastecimiento_items"

    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey("pedidos_reabastecimiento.id", ondelete="CASCADE"), nullable=False)
    item_inventario_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=False)
    cantidad_solicitada = Column(Numeric(8, 2), nullable=False)
    cantidad_recibida = Column(Numeric(8, 2), nullable=True)
    precio_unitario = Column(Numeric(10, 2), nullable=True)
    costo_total = Column(Numeric(10, 2), nullable=True)
    razon_solicitud = Column(String(100), nullable=True)


class ReglaReabastecimiento(Base):
    """Min/máx de stock por item (+ opcionalmente por punto_venta) usado por el
    algoritmo de sugerencias de abastecimiento. punto_venta_id NULL = regla
    global de respaldo, usada si no hay una regla específica de esa tienda."""

    __tablename__ = "reglas_reabastecimiento"

    id = Column(Integer, primary_key=True)
    item_inventario_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=False)
    punto_venta_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=True)
    stock_minimo = Column(Numeric(10, 2), nullable=False)
    stock_maximo = Column(Numeric(10, 2), nullable=False)
    consumo_diario_base = Column(Numeric(10, 2), nullable=True)
    factor_sabado = Column(Numeric(3, 2), nullable=False, default=1.30)
    factor_domingo = Column(Numeric(3, 2), nullable=False, default=1.50)
    cantidad_fija_diaria = Column(Numeric(10, 2), nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("item_inventario_id", "punto_venta_id", name="uq_reglas_reab_item_punto"),
        CheckConstraint("stock_maximo >= stock_minimo", name="ck_reglas_reab_max_ge_min"),
    )
