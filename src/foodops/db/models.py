"""Modelos SQLAlchemy para BD"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, CheckConstraint, ForeignKey, Enum, Text, JSON, BigInteger, TIMESTAMP, UniqueConstraint, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

# Enums
class UserRol(str, enum.Enum):
    ADMIN = "admin"
    GERENTE_GENERAL = "gerente_general"
    GERENTE_CENTRAL = "gerente_central"
    GERENTE_PUNTO = "gerente_punto"
    RESP_TIENDA = "resp_tienda"
    REPARTIDOR = "repartidor"
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

    # Impresión por agente de tienda (docs/DISENO_IMPRESION.md §3). El token
    # del agente NO va aquí: vive en tokens_agente.
    impresora_ip = Column(String(45), nullable=True)
    impresora_puerto = Column(Integer, nullable=False, default=9100, server_default="9100")
    impresora_activa = Column(Boolean, nullable=False, default=False, server_default="false")
    # Si es False, nunca se generan trabajos ABRIR_CAJON para esta tienda.
    cajon_activo = Column(Boolean, nullable=False, default=False, server_default="false")
    
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
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="usuarios")
    punto = relationship("PuntoVenta", back_populates="usuarios")

    # Un rol de tienda sin tienda asignada produce una sesión inoperable
    # (ver migración 010). El enum guarda el NOMBRE del miembro, no su valor.
    __table_args__ = (
        CheckConstraint(
            "punto_id IS NOT NULL OR rol::text IN ('ADMIN', 'GERENTE_GENERAL', 'GERENTE_CENTRAL')",
            name="ck_usuarios_tienda_segun_rol",
        ),
    )

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
    dinero_recibido = Column(Float)  # lo que el vendedor estimó al crear la orden
    vuelto = Column(Float)           # vuelto ESPERADO, calculado por el vendedor
    es_domicilio = Column(Boolean, default=False)
    notas_especiales = Column(Text)
    tomada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    actualizado_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Estado de cobro: eje independiente de `estado` (que es exclusivamente
    # de cocina - ver docs/AUDITORIA_COBRO_EFECTIVO.md, hallazgo crítico).
    # String simple, no Enum nativo de Postgres, igual que CajaDiaria.estado/
    # TransaccionVenta.estado/PedidoReabastecimiento.estado en el resto del
    # proyecto - evita el ALTER TYPE ADD VALUE para agregar un estado futuro.
    # Valores: "pendiente_recibir" | "cobrada". Las órdenes que no son en
    # efectivo nacen directamente en "cobrada" (tarjeta/transferencia se
    # confirman al momento, no hay entrega física de efectivo que esperar).
    estado_cobro = Column(String(20), nullable=False, default="cobrada")
    # Confirmados por el responsable al recibir el efectivo - distintos de
    # dinero_recibido/vuelto (el estimado del vendedor), aunque coincidan.
    monto_recibido = Column(Float, nullable=True)
    vuelto_entregado = Column(Float, nullable=True)
    confirmado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    confirmado_at = Column(DateTime, nullable=True)

    punto = relationship("PuntoVenta", back_populates="ordenes")
    items = relationship("OrdenItem", back_populates="orden")
    tomada_por_usuario = relationship("Usuario", foreign_keys=[tomada_por])

    # Único por tienda, no global: los números previos al multitienda no
    # llevaban la tienda en el prefijo (ver migración 010).
    __table_args__ = (
        UniqueConstraint("punto_id", "numero_orden", name="uq_ordenes_punto_numero"),
    )

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


class TipoVenta(str, enum.Enum):
    INDIVIDUAL = "individual"
    COMBO = "combo"
    INICIATIVA = "iniciativa"


class TransaccionVenta(Base):
    __tablename__ = "transacciones_venta"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=True)

    tipo_venta = Column(Enum(TipoVenta), nullable=False, default=TipoVenta.INDIVIDUAL)
    nombre_iniciativa = Column(String(100), nullable=True)

    cliente_nombre = Column(String(100), nullable=True)
    cliente_telefono = Column(String(20), nullable=True)
    cliente_direccion = Column(Text, nullable=True)
    tipo_cliente = Column(String(20), nullable=False, default="para_llevar")

    precio_venta = Column(Float, nullable=False)
    costo_total = Column(Float, nullable=False, default=0)
    margen_bruto = Column(Float, nullable=False, default=0)
    margen_pct = Column(Float, nullable=False, default=0)

    metodo_pago = Column(String(50), nullable=True)
    items_json = Column(JSON, nullable=False, default=list)
    requerimientos_especiales = Column(Text, nullable=True)
    estado = Column(String(50), nullable=False, default="completada")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True)
    usuario_id = Column(Integer, nullable=True)
    punto_id = Column(Integer, nullable=True)
    accion = Column(String(60), nullable=False)
    entidad = Column(String(40), nullable=False)
    entidad_id = Column(String(40), nullable=True)
    detalle = Column(JSON, nullable=True)
    ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Impresión por agente de tienda (docs/DISENO_IMPRESION.md §5, §6)
# ---------------------------------------------------------------------------
# tipo/estado son String + CHECK, no Enum nativo: misma convención que
# ordenes.estado_cobro (migración 011), evita ALTER TYPE y la confusión
# nombre/valor del Enum de SQLAlchemy.

TRABAJO_TIPO_TICKET = "ticket"
TRABAJO_TIPO_ABRIR_CAJON = "abrir_cajon"

TRABAJO_ESTADO_PENDIENTE = "pendiente"
TRABAJO_ESTADO_IMPRIMIENDO = "imprimiendo"
TRABAJO_ESTADO_OK = "ok"
TRABAJO_ESTADO_ERROR = "error"

# Motivo fijo del trabajo ABRIR_CAJON que crea confirmar-cobro.
MOTIVO_CAJON_COBRO_EFECTIVO = "cobro_efectivo"


class TrabajoImpresion(Base):
    __tablename__ = "trabajos_impresion"

    id = Column(BigInteger, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    tipo = Column(String(20), nullable=False)
    # JSON estructurado, NUNCA HTML: el agente arma el ESC/POS.
    payload = Column(JSON, nullable=False, default=dict)
    estado = Column(String(20), nullable=False, default=TRABAJO_ESTADO_PENDIENTE)
    solicitado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    # Obligatorio para ABRIR_CAJON manual; "cobro_efectivo" para el automático.
    motivo = Column(String(200), nullable=True)
    orden_id = Column(Integer, ForeignKey("ordenes.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    tomado_at = Column(DateTime, nullable=True)
    completado_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("tipo IN ('ticket', 'abrir_cajon')", name="ck_trabajos_impresion_tipo"),
        CheckConstraint(
            "estado IN ('pendiente', 'imprimiendo', 'ok', 'error')",
            name="ck_trabajos_impresion_estado",
        ),
        Index("ix_trabajos_impresion_punto_estado", "punto_id", "estado"),
        Index("ix_trabajos_impresion_orden", "orden_id"),
        # Parcial: a lo sumo un ABRIR_CAJON por orden, pero TICKET sin límite
        # (reimpresiones). Los ABRIR_CAJON manuales tienen orden_id NULL y en
        # Postgres los NULL no chocan en un índice único.
        Index(
            "ux_trabajos_impresion_cajon_por_orden",
            "orden_id",
            unique=True,
            postgresql_where=text("tipo = 'abrir_cajon'"),
        ),
    )


class TokenAgente(Base):
    __tablename__ = "tokens_agente"

    id = Column(Integer, primary_key=True)
    punto_id = Column(Integer, ForeignKey("puntos_venta.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)  # sha256 hex
    activo = Column(Boolean, nullable=False, default=True)
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revocado_at = Column(DateTime, nullable=True)
    # Heartbeat: se actualiza en cada request autenticado del agente.
    ultima_conexion_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_tokens_agente_punto_activo", "punto_id", "activo"),
        Index(
            "ux_tokens_agente_punto_unico_activo",
            "punto_id",
            unique=True,
            postgresql_where=text("activo = true"),
        ),
    )
