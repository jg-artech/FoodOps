"""Pydantic schemas para validación"""

from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, EmailStr, Field

from foodops.db.models import MetodoPago, OrdenEstado, TipoVenta

# Reusable annotated types
NombreStr = Annotated[str, Field(max_length=100)]
TelefonoStr = Annotated[str, Field(max_length=20)]
DireccionStr = Annotated[str, Field(max_length=200)]
RequerimientosStr = Annotated[str, Field(max_length=500)]
Precio = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]
Cantidad = Annotated[int, Field(ge=1, le=999)]


class UsuarioCreate(BaseModel):
    username: Annotated[str, Field(max_length=100)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    nombre_completo: NombreStr


class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str
    nombre_completo: str

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: Annotated[str, Field(max_length=100)]
    password: Annotated[str, Field(max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrdenItemCreate(BaseModel):
    producto: Annotated[str, Field(max_length=100)]
    cantidad: Cantidad
    precio_unitario: Precio
    especiales: Optional[RequerimientosStr] = None


class OrdenCreate(BaseModel):
    cliente_nombre: Optional[NombreStr] = None
    cliente_telefono: Optional[TelefonoStr] = None
    cliente_direccion: Optional[DireccionStr] = None
    metodo_pago: MetodoPago
    items: List[OrdenItemCreate]
    es_domicilio: bool = False
    notas_especiales: Optional[RequerimientosStr] = None
    dinero_recibido: Optional[Precio] = None
    vuelto: Optional[Precio] = None


class OrdenResponse(BaseModel):
    id: int
    numero_orden: str
    estado: OrdenEstado
    total: Decimal
    created_at: str

    class Config:
        from_attributes = True


class ItemTransaccion(BaseModel):
    nombre: Annotated[str, Field(max_length=100)]
    cantidad: Annotated[float, Field(ge=0)]
    unidad: str = "pieza"
    precio_unitario: Annotated[float, Field(ge=0)]
    costo_unitario: Annotated[float, Field(ge=0)] = 0
    subtotal: Annotated[float, Field(ge=0)]
    tipo_pieza: Optional[Annotated[str, Field(max_length=50)]] = None
    producto_menu_id: Optional[int] = None
    # item_inventario_id de los componentes "elegible=true" que el cliente eligió
    # para este producto (p.ej. la guarnición elegida dentro de un combo). Si es
    # None, ningún componente elegible se registra (comportamiento previo).
    componentes_elegidos: Optional[List[int]] = None


class CrearTransaccionRequest(BaseModel):
    orden_id: Optional[int] = None
    tipo_venta: TipoVenta = TipoVenta.INDIVIDUAL
    nombre_iniciativa: Optional[NombreStr] = None
    cliente_nombre: Optional[NombreStr] = None
    cliente_telefono: Optional[TelefonoStr] = None
    cliente_direccion: Optional[DireccionStr] = None
    tipo_cliente: Annotated[str, Field(max_length=30)] = "para_llevar"
    precio_venta: Annotated[float, Field(ge=0)]
    costo_total: Annotated[float, Field(ge=0)] = 0
    margen_bruto: float = 0
    margen_pct: float = 0
    metodo_pago: MetodoPago
    items: List[ItemTransaccion]
    requerimientos_especiales: Optional[RequerimientosStr] = None
