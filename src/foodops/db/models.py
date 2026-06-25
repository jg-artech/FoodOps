"""Modelos SQLAlchemy para BD"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

# Enums
class UserRol(str, enum.Enum):
    ADMIN = "admin"
    GERENTE_PUNTO = "gerente_punto"
    TOMADOR_ORDEN = "tomador_orden"
    COCINERO = "cocinero"
    BODEGUERO = "bodeguero"

class OrdenEstado(str, enum.Enum):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    LISTO = "listo"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"

class MetodoPago(str, enum.Enum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"

# Modelos

class Empresa(Base):
    __tablename__ = "empresas"
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(255), nullable=False)
    nit = Column(String(20), unique=True, nullable=False)
    registro_tributario = Column(String(20))
    telefono = Column(String(20))
    email = Column(String(255))
    direccion = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    puntos = relationship("PuntoVenta", back_populates="empresa")
    usuarios = relationship("Usuario", back_populates="empresa")

class PuntoVenta(Base):
    __tablename__ = "puntos_venta"
    
    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    nombre = Column(String(255), nullable=False)
    direccion = Column(Text)
    telefono = Column(String(20))
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    empresa = relationship("Empresa", back_populates="puntos")
    usuarios = relationship("Usuario", back_populates="punto")
    ordenes = relationship("Orden", back_populates="punto")

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nombre_completo = Column(String(255))
    rol = Column(Enum(UserRol), default=UserRol.TOMADOR_ORDEN)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    empresa = relationship("Empresa", back_populates="usuarios")
    punto = relationship("PuntoVenta", back_populates="usuarios")

class Orden(Base):
    __tablename__ = "ordenes"
    
    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    numero_orden = Column(String(50), nullable=False)
    cliente_nombre = Column(String(255))
    cliente_telefono = Column(String(20))
    cliente_direccion = Column(Text)
    estado = Column(Enum(OrdenEstado), default=OrdenEstado.PENDIENTE)
    metodo_pago = Column(Enum(MetodoPago))
    total = Column(Float, nullable=False)
    dinero_recibido = Column(Float)
    vuelto = Column(Float)
    es_domicilio = Column(Boolean, default=False)
    notas_especiales = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    actualizado_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    punto = relationship("PuntoVenta", back_populates="ordenes")
    items = relationship("OrdenItem", back_populates="orden")

class OrdenItem(Base):
    __tablename__ = "orden_items"
    
    id = Column(Integer, primary_key=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=False)
    producto = Column(String(255), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    especiales = Column(Text)
    
    orden = relationship("Orden", back_populates="items")
