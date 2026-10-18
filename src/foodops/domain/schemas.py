"""Pydantic schemas para validación"""

from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from foodops.db.models import MetodoPago, OrdenEstado, TipoVenta

# Reusable annotated types
NombreStr = Annotated[str, Field(max_length=200)]
TelefonoStr = Annotated[str, Field(max_length=20)]
DireccionStr = Annotated[str, Field(max_length=200)]
RequerimientosStr = Annotated[str, Field(max_length=500)]
Precio = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]
Cantidad = Annotated[int, Field(ge=1, le=999)]


class UsuarioCreate(BaseModel):
    username: Annotated[str, Field(max_length=100)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    nombre_completo: Optional[NombreStr] = None
    # Valor de UserRol (ej. "tomador_orden"), validado en el router contra
    # el enum real - aquí es solo un string para no importar el modelo.
    rol: Annotated[str, Field(max_length=30)]
    # Obligatorio salvo para los roles de ROLES_MULTI_TIENDA (ver core.auth).
    # El router valida que la tienda exista y que el rol la necesite.
    punto_id: Optional[int] = None


class UsuarioUpdate(BaseModel):
    """Todos los campos opcionales: solo se actualiza lo que venga."""
    nombre_completo: Optional[NombreStr] = None
    rol: Optional[Annotated[str, Field(max_length=30)]] = None
    punto_id: Optional[int] = None
    activo: Optional[bool] = None
    # Resetear contraseña desde el panel de administración, no hay endpoint
    # de "cambiar mi contraseña" todavía.
    password: Optional[Annotated[str, Field(min_length=8, max_length=128)]] = None


class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str
    nombre_completo: Optional[str] = None
    rol: str
    punto_id: Optional[int] = None
    punto_nombre: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True


class PuntoVentaCreate(BaseModel):
    nombre: NombreStr
    direccion: Optional[DireccionStr] = None
    telefono: Optional[TelefonoStr] = None


class PuntoVentaUpdate(BaseModel):
    nombre: Optional[NombreStr] = None
    direccion: Optional[DireccionStr] = None
    telefono: Optional[TelefonoStr] = None


class LoginRequest(BaseModel):
    username: Annotated[str, Field(max_length=200)]
    password: Annotated[str, Field(max_length=128)]

    @field_validator("username")
    @classmethod
    def _trim_username(cls, v: str) -> str:

        # Autocomplete/teclados móviles a veces agregan espacio final


        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrdenItemCreate(BaseModel):
    producto: Annotated[str, Field(max_length=200)]
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


class ConfirmarCobroRequest(BaseModel):
    """Lo que el responsable confirma al recibir el efectivo físicamente -
    puede diferir del dinero_recibido/vuelto que estimó el vendedor al
    crear la orden, por eso son campos obligatorios y no se copian solos."""
    monto_recibido: Precio
    vuelto_entregado: Precio


class OrdenResponse(BaseModel):
    id: int
    numero_orden: str
    estado: OrdenEstado
    total: Decimal
    created_at: str

    class Config:
        from_attributes = True


class ItemTransaccion(BaseModel):
    nombre: Annotated[str, Field(max_length=200)]
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
