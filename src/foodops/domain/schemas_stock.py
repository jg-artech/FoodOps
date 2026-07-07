"""Pydantic schemas para Etapa 2.5: stock en vivo, recetas y reabastecimiento"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

Monto = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]
Cantidad = Annotated[float, Field(gt=0, le=9999)]
RazonStr = Annotated[str, Field(max_length=100)]


class TipoPedidoReabastecimiento(str, enum.Enum):
    COMPRA_PROVEEDOR = "compra_proveedor"
    SOLICITUD_CENTRAL = "solicitud_central"


class EstadoPedidoReabastecimiento(str, enum.Enum):
    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"


class RazonSolicitud(str, enum.Enum):
    STOCK_BAJO = "stock_bajo"
    PROYECCION_DEMANDA = "proyeccion_demanda"
    FUGA_DETECTADA = "fuga_detectada"
    OTRO = "otro"


class TransaccionComponenteResponse(BaseModel):
    id: int
    transaccion_id: int
    item_inventario_id: int
    cantidad: Decimal
    tipo_origen: str
    created_at: datetime

    class Config:
        from_attributes = True


class StockActualResponse(BaseModel):
    item_id: int
    nombre: str
    unidad: str
    cantidad_apertura: Decimal
    consumo_teorico: Decimal
    stock_estimado: Decimal
    cantidad_cierre: Optional[Decimal] = None
    fuga_detectada: Optional[Decimal] = None


class ProyeccionItemResponse(BaseModel):
    item_id: int
    nombre: str
    consumo_promedio_diario: Decimal
    stock_proyectado: Decimal


class RecomendacionReabastecimientoResponse(BaseModel):
    item_id: int
    nombre: str
    stock_actual: Decimal
    consumo_diario_promedio: Decimal
    dias_disponibles: Optional[Decimal] = None
    recomendacion: str
    cantidad_sugerida: Decimal


class PedidoReabastecimientoItemCreate(BaseModel):
    item_id: int
    cantidad: Cantidad
    razon: Optional[RazonSolicitud] = None


class PedidoReabastecimientoCreate(BaseModel):
    tipo: TipoPedidoReabastecimiento = TipoPedidoReabastecimiento.SOLICITUD_CENTRAL
    items: List[PedidoReabastecimientoItemCreate]


class PedidoReabastecimientoItemResponse(BaseModel):
    id: int
    item_inventario_id: int
    nombre: Optional[str] = None
    cantidad_solicitada: Decimal
    cantidad_recibida: Optional[Decimal] = None
    precio_unitario: Optional[Decimal] = None
    costo_total: Optional[Decimal] = None
    razon_solicitud: Optional[str] = None

    class Config:
        from_attributes = True


class PedidoReabastecimientoResponse(BaseModel):
    id: int
    punto_id: int
    tipo: str
    estado: str
    total_estimado: Optional[Decimal] = None
    creado_por: int
    confirmado_por: Optional[int] = None
    created_at: datetime
    confirmado_at: Optional[datetime] = None
    items: List[PedidoReabastecimientoItemResponse] = []

    class Config:
        from_attributes = True


class RecibirPedidoItem(BaseModel):
    item_id: int
    cantidad: Annotated[float, Field(ge=0, le=9999)]


class RecibirPedidoRequest(BaseModel):
    items_recibidos: List[RecibirPedidoItem]


class DashboardGerenteResponse(BaseModel):
    punto_id: int
    stock: List[StockActualResponse]
    recomendaciones: List[RecomendacionReabastecimientoResponse]
    pedidos_pendientes: List[PedidoReabastecimientoResponse]
    resumen: dict
