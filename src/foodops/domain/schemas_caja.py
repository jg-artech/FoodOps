"""Pydantic schemas para Módulo D: Caja y Tienda"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

# Reusable annotated types (same limits as domain/schemas.py)
Monto = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]
MontoPositivo = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=10, decimal_places=2)]
Cantidad = Annotated[float, Field(ge=0, le=9999)]
CantidadPositiva = Annotated[float, Field(gt=0, le=9999)]
DescripcionStr = Annotated[str, Field(max_length=200)]
MotivoStr = Annotated[str, Field(max_length=200)]
NombreStr = Annotated[str, Field(max_length=100)]
UnidadStr = Annotated[str, Field(max_length=20)]


class CategoriaGasto(str, enum.Enum):
    INSUMOS = "insumos"
    SERVICIOS = "servicios"
    SUELDOS = "sueldos"
    TRANSPORTE = "transporte"
    PUBLICIDAD = "publicidad"
    OTROS = "otros"


class TipoItemInventario(str, enum.Enum):
    VENDIBLE = "vendible"
    DESECHABLE = "desechable"
    INSUMO = "insumo"


class MomentoInventario(str, enum.Enum):
    APERTURA = "apertura"
    CIERRE = "cierre"


# ---------------------------------------------------------------------------
# Caja diaria
# ---------------------------------------------------------------------------


class CajaDiariaCreate(BaseModel):
    fondo_inicial: Monto


class CajaDiariaCerrarRequest(BaseModel):
    efectivo_contado: Monto


class CajaDiariaResponse(BaseModel):
    id: int
    punto_id: int
    fecha: date
    fondo_inicial: Decimal
    efectivo_esperado: Optional[Decimal] = None
    efectivo_contado: Optional[Decimal] = None
    descuadre: Optional[Decimal] = None
    estado: str
    abierta_por: int
    cerrada_por: Optional[int] = None
    observacion_gerente: Optional[str] = None
    created_at: datetime
    cerrada_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CajaActualResponse(BaseModel):
    id: int
    fondo_inicial: Decimal
    gastos_hoy: Decimal
    fondos_entregados: Decimal
    estado: str


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------


class GastoCreate(BaseModel):
    categoria: CategoriaGasto
    descripcion: DescripcionStr
    monto: MontoPositivo


class GastoResponse(BaseModel):
    id: int
    caja_id: int
    punto_id: int
    categoria: str
    descripcion: str
    monto: Decimal
    registrado_por: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Desperdicios
# ---------------------------------------------------------------------------


class DesperdicioCreate(BaseModel):
    item_inventario_id: Optional[int] = None
    producto_id: Optional[int] = None
    cantidad: CantidadPositiva
    unidad: UnidadStr
    motivo: Optional[MotivoStr] = None


class DesperdicioResponse(BaseModel):
    id: int
    punto_id: int
    producto_id: Optional[int] = None
    item_inventario_id: Optional[int] = None
    cantidad: Decimal
    unidad: str
    motivo: Optional[str] = None
    costo_estimado: Optional[Decimal] = None
    registrado_por: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Items de inventario
# ---------------------------------------------------------------------------


class ItemInventarioCreate(BaseModel):
    nombre: NombreStr
    tipo: TipoItemInventario
    unidad: UnidadStr
    producto_menu_id: Optional[int] = None
    orden_conteo: Annotated[int, Field(ge=0, le=9999)]


class ItemInventarioUpdate(BaseModel):
    nombre: Optional[NombreStr] = None
    tipo: Optional[TipoItemInventario] = None
    unidad: Optional[UnidadStr] = None
    producto_menu_id: Optional[int] = None
    orden_conteo: Optional[Annotated[int, Field(ge=0, le=9999)]] = None
    activo: Optional[bool] = None


class ItemInventarioResponse(BaseModel):
    id: int
    punto_id: Optional[int] = None
    nombre: str
    tipo: str
    unidad: str
    producto_menu_id: Optional[int] = None
    orden_conteo: int
    activo: bool

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Inventario diario
# ---------------------------------------------------------------------------


class InventarioDetalleItem(BaseModel):
    item_id: int
    cantidad: Cantidad


class InventarioDiarioSubmit(BaseModel):
    items: List[InventarioDetalleItem]


class InventarioDetalleResponse(BaseModel):
    item_id: int
    nombre: str
    unidad: str
    cantidad: Decimal

    class Config:
        from_attributes = True


class InventarioDiarioResponse(BaseModel):
    id: int
    caja_id: int
    punto_id: int
    fecha: date
    momento: str
    completado: bool
    detalle: List[InventarioDetalleResponse] = []

    class Config:
        from_attributes = True


class ConsumoItemResponse(BaseModel):
    item_id: int
    nombre: str
    apertura: Decimal
    recibido_envios: Decimal
    cierre: Decimal
    desperdicio: Decimal
    consumo_real: Decimal
    consumo_teorico: Decimal
    diferencia: Decimal


# ---------------------------------------------------------------------------
# Fondos de repartidor
# ---------------------------------------------------------------------------


class FondoRepartidorCreate(BaseModel):
    repartidor_id: int
    monto_entregado: MontoPositivo


class FondoRepartidorLiquidarRequest(BaseModel):
    monto_liquidado: Monto


class FondoRepartidorResponse(BaseModel):
    id: int
    caja_id: int
    repartidor_id: int
    monto_entregado: Decimal
    monto_liquidado: Optional[Decimal] = None
    diferencia: Optional[Decimal] = None
    estado: str
    entregado_at: datetime
    liquidado_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Transacciones de pedidos (compras / envíos entre tienda y central)
# ---------------------------------------------------------------------------


class ItemPedido(BaseModel):
    item_id: int
    nombre: NombreStr
    cantidad: CantidadPositiva
    unidad: UnidadStr


class TransaccionPedidoCreate(BaseModel):
    tipo: Annotated[str, Field(max_length=30)]
    items: List[ItemPedido]


class TransaccionPedidoResponse(BaseModel):
    id: int
    punto_id: int
    tipo: str
    items_json: list
    estado: str
    creado_por: int
    completado_por: Optional[int] = None
    created_at: datetime
    completado_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Reporte de cierre
# ---------------------------------------------------------------------------


class ReporteCierreResponse(BaseModel):
    caja: CajaDiariaResponse
    gastos: List[GastoResponse]
    desperdicios: List[DesperdicioResponse]
    fondos_repartidor: List[FondoRepartidorResponse]
    consumo: List[ConsumoItemResponse]
    resumen: dict


class ReporteConsumoResponse(BaseModel):
    fecha: date
    items: List[ConsumoItemResponse]
