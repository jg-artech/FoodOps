"""Pydantic schemas para Etapa 2.5: stock en vivo, recetas y reabastecimiento"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

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


# ---------------------------------------------------------------------------
# CRUD de productos_menu + su receta, desde ConfigView
# ---------------------------------------------------------------------------


class ComponenteProductoCreate(BaseModel):
    item_inventario_id: int
    cantidad: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=8, decimal_places=2)]
    elegible: bool = False
    # Solo tienen sentido si elegible=True: agrupan varios componentes del mismo
    # producto en un "elige 1" independiente (p.ej. grupo 1 "Pieza de Pollo",
    # grupo 2 "Guarnición"). Se normalizan a None si elegible=False.
    grupo_elegible: Optional[Annotated[int, Field(ge=1, le=50)]] = None
    nombre_grupo: Optional[Annotated[str, Field(max_length=100)]] = None

    @model_validator(mode="after")
    def _normalizar_grupo(self) -> "ComponenteProductoCreate":
        if not self.elegible:
            self.grupo_elegible = None
            self.nombre_grupo = None
        elif self.grupo_elegible is not None and not (self.nombre_grupo or "").strip():
            raise ValueError("nombre_grupo es requerido cuando se asigna grupo_elegible")
        return self


class ProductoConComponentesCreate(BaseModel):
    nombre: Annotated[str, Field(max_length=100)]
    precio: Monto
    # Categoría real del catálogo (pollos|costillas|combos|guarniciones|extras|...) -
    # el usuario puede crear categorías nuevas libremente desde ConfigView, así que
    # esto es un string libre (con límite de longitud), no el enum productos|combos
    # de dos valores que traía la spec original.
    categoria: Annotated[str, Field(max_length=30)]
    unidad: Annotated[str, Field(max_length=20)]
    descripcion: Optional[Annotated[str, Field(max_length=200)]] = None
    # La spec pedía min_items=1, pero ya existen productos reales sin receta
    # mapeable (Papa al vapor, Ensalada Rusa, Porción Extra - ver
    # project-stock-reabastecimiento) porque no hay item_inventario equivalente.
    # Exigir mínimo 1 aquí bloquearía crear ese mismo tipo de producto vía UI.
    componentes: Annotated[List[ComponenteProductoCreate], Field(max_length=20)] = []


class ProductoConComponentesUpdate(ProductoConComponentesCreate):
    pass


class ComponenteProductoResponse(BaseModel):
    item_id: int
    item_nombre: str
    cantidad: Decimal
    elegible: bool
    grupo_elegible: Optional[int] = None
    nombre_grupo: Optional[str] = None


class ProductoConComponentesResponse(BaseModel):
    id: int
    nombre: str
    precio: Decimal
    categoria: str
    tipo: str
    unidad: str
    descripcion: Optional[str] = None
    activo: bool
    componentes: List[ComponenteProductoResponse] = []
