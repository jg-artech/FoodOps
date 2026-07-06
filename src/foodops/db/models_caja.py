"""Modelos SQLAlchemy para Módulo D: Caja y Tienda (efectivo, inventario diario, gastos, desperdicios, fondos de repartidor)"""

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
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from foodops.db.models import Base


class CajaDiaria(Base):
    __tablename__ = "cajas_diarias"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    fondo_inicial = Column(Numeric(10, 2), nullable=False)
    efectivo_esperado = Column(Numeric(10, 2))
    efectivo_contado = Column(Numeric(10, 2))
    descuadre = Column(Numeric(10, 2))
    estado = Column(String(20), nullable=False, default="abierta")
    abierta_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cerrada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observacion_gerente = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    cerrada_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("punto_id", "fecha", name="uq_cajas_punto_fecha"),)


class Gasto(Base):
    __tablename__ = "gastos"

    id = Column(Integer, primary_key=True)
    caja_id = Column(Integer, ForeignKey("cajas_diarias.id"), nullable=False)
    punto_id = Column(Integer, nullable=False)
    categoria = Column(String(40), nullable=False)
    descripcion = Column(String(200), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (CheckConstraint("monto > 0", name="ck_gastos_monto_positivo"),)


class Desperdicio(Base):
    __tablename__ = "desperdicios"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    producto_id = Column(Integer, nullable=True)
    item_inventario_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=True)
    cantidad = Column(Numeric(8, 2), nullable=False)
    unidad = Column(String(20), nullable=False)
    motivo = Column(String(200), nullable=True)
    costo_estimado = Column(Numeric(10, 2), nullable=True)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_desperdicios_cantidad_positiva"),)


class ItemInventario(Base):
    __tablename__ = "items_inventario"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, nullable=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)
    unidad = Column(String(20), nullable=False)
    producto_menu_id = Column(Integer, nullable=True)
    orden_conteo = Column(Integer, nullable=False)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventarioDiario(Base):
    __tablename__ = "inventarios_diarios"

    id = Column(Integer, primary_key=True)
    caja_id = Column(Integer, ForeignKey("cajas_diarias.id"), nullable=False)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    momento = Column(String(20), nullable=False)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    completado = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("punto_id", "fecha", "momento", name="uq_inv_diario_punto_fecha_momento"),
    )


class InventarioDetalle(Base):
    __tablename__ = "inventario_detalle"

    id = Column(BigInteger, primary_key=True)
    inventario_id = Column(Integer, ForeignKey("inventarios_diarios.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items_inventario.id"), nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint("inventario_id", "item_id", name="uq_inv_detalle_inventario_item"),
        CheckConstraint("cantidad >= 0", name="ck_inv_detalle_cantidad_no_negativa"),
    )


class FondoRepartidor(Base):
    __tablename__ = "fondos_repartidor"

    id = Column(Integer, primary_key=True)
    caja_id = Column(Integer, ForeignKey("cajas_diarias.id"), nullable=False)
    repartidor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    monto_entregado = Column(Numeric(10, 2), nullable=False)
    monto_liquidado = Column(Numeric(10, 2), nullable=True)
    diferencia = Column(Numeric(10, 2), nullable=True)
    estado = Column(String(20), nullable=False, default="entregado")
    entregado_at = Column(DateTime, default=datetime.utcnow)
    liquidado_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TransaccionPedido(Base):
    __tablename__ = "transacciones_pedidos"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    tipo = Column(String(30), nullable=False)
    items_json = Column(JSON, nullable=False)
    estado = Column(String(20), nullable=False, default="pendiente")
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    completado_por = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completado_at = Column(DateTime, nullable=True)
