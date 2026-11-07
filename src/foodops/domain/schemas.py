"""Pydantic schemas para validación"""

from decimal import Decimal
from typing import Annotated, List, Optional

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from foodops.db.models import MetodoPago, OrdenEstado, TipoVenta

# Reusable annotated types
NombreStr = Annotated[str, Field(max_length=200)]
TelefonoStr = Annotated[str, Field(max_length=20)]
DireccionStr = Annotated[str, Field(max_length=200)]
RequerimientosStr = Annotated[str, Field(max_length=500)]
Precio = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=10, decimal_places=2)]
Cantidad = Annotated[int, Field(ge=1, le=999)]

# ---------------------------------------------------------------------------
# Nombre del cliente al cobrar
# ---------------------------------------------------------------------------
# El personal llama al cliente por este nombre al entregar la orden, así que
# es obligatorio en todo cobro (efectivo, tarjeta y transferencia).
# 100 caracteres: el límite real de transacciones_venta.cliente_nombre (la
# columna de ordenes admite 255, pero el mismo nombre se copia a la
# transacción).
CLIENTE_NOMBRE_MAX = 100
CLIENTE_NOMBRE_MIN_UTILES = 2
MSG_CLIENTE_NOMBRE = "El nombre del cliente es obligatorio (al menos 2 letras o números)"


def normalizar_cliente_nombre(valor: Optional[str]) -> str:
    """Quita espacios de los extremos y exige 2 caracteres útiles (letras o
    números; "  ", ".." o "-" no sirven para llamar a nadie)."""
    if valor is None:
        raise PydanticCustomError("cliente_nombre_obligatorio", MSG_CLIENTE_NOMBRE)
    limpio = " ".join(str(valor).split())
    if sum(1 for c in limpio if c.isalnum()) < CLIENTE_NOMBRE_MIN_UTILES:
        raise PydanticCustomError("cliente_nombre_obligatorio", MSG_CLIENTE_NOMBRE)
    if len(limpio) > CLIENTE_NOMBRE_MAX:
        raise PydanticCustomError(
            "cliente_nombre_largo",
            "El nombre del cliente admite como máximo {max} caracteres",
            {"max": CLIENTE_NOMBRE_MAX},
        )
    return limpio


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
    # Obligatorio para los tres métodos de pago (ver normalizar_cliente_nombre).
    # Optional + validate_default para que "falta el campo" dé el mismo
    # mensaje en español que "viene vacío".
    cliente_nombre: Optional[str] = Field(default=None, validate_default=True)
    cliente_telefono: Optional[TelefonoStr] = None
    cliente_direccion: Optional[DireccionStr] = None
    metodo_pago: MetodoPago
    items: List[OrdenItemCreate]
    es_domicilio: bool = False
    notas_especiales: Optional[RequerimientosStr] = None
    dinero_recibido: Optional[Precio] = None
    vuelto: Optional[Precio] = None

    @field_validator("cliente_nombre", mode="before")
    @classmethod
    def _cliente_nombre_obligatorio(cls, v):
        return normalizar_cliente_nombre(v)


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
    # Obligatorio solo sin orden_id (tarjeta/transferencia directas): con
    # orden, el nombre ya se validó al crearla en POST /api/ordenes/.
    cliente_nombre: Optional[Annotated[str, Field(max_length=CLIENTE_NOMBRE_MAX)]] = None
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

    @model_validator(mode="after")
    def _cliente_nombre_si_no_hay_orden(self):
        # Efectivo sin orden no se valida aquí: el endpoint lo rechaza con el
        # 400 de siempre ("no existe efectivo sin orden", CLAUDE.md), y ese
        # mensaje no debe quedar tapado por el del nombre.
        if self.orden_id is None and self.metodo_pago != MetodoPago.EFECTIVO:
            self.cliente_nombre = normalizar_cliente_nombre(self.cliente_nombre)
        return self


# ---------------------------------------------------------------------------
# Datos de facturación (fase 1: solo captura; ver migración 013)
# ---------------------------------------------------------------------------
# NIT: dígitos, con guion opcional y dígito verificador 0-9 o K. Misma regla
# en el frontend (solo para avisar); aquí es donde se rechaza.
# TODO(facturación): decidir si "CF" (consumidor final) es un NIT válido.
# Por ahora se rechaza: no cumple el formato.
# Equivale a ^\d+(-?[0-9K])?$ del frontend: en Python \d también acepta
# dígitos Unicode (árabes, etc.), por eso aquí va [0-9] con fullmatch.
NIT_REGEX = re.compile(r"[0-9]+(-?[0-9K])?")
NIT_MAX = 20
NOMBRE_FISCAL_MAX = 200
DIRECCION_FISCAL_MAX = 255


def normalizar_nit(valor: Optional[str]) -> str:
    """Quita espacios de los extremos y pasa a mayúsculas. Un espacio en
    medio ("123 456") no se arregla: es formato inválido."""
    if valor is None or not str(valor).strip():
        raise PydanticCustomError("nit_obligatorio", "El NIT es obligatorio cuando se requiere factura")
    nit = str(valor).strip().upper()
    if len(nit) > NIT_MAX or not NIT_REGEX.fullmatch(nit):
        raise PydanticCustomError(
            "nit_invalido",
            "NIT inválido: use solo dígitos, con guion y dígito verificador opcionales (ej. 1234567-8 o 1234567-K)",
        )
    return nit


def _texto_fiscal(valor: Optional[str], campo: str, maximo: int) -> str:
    limpio = " ".join(str(valor).split()) if valor is not None else ""
    if not limpio:
        raise PydanticCustomError(
            "dato_fiscal_obligatorio",
            "{campo} es obligatorio cuando se requiere factura",
            {"campo": campo},
        )
    if len(limpio) > maximo:
        raise PydanticCustomError(
            "dato_fiscal_largo",
            "{campo} admite como máximo {max} caracteres",
            {"campo": campo, "max": maximo},
        )
    return limpio


class DatosFacturaRequest(BaseModel):
    """Body de PUT /api/ordenes/{id}/datos-factura. extra="forbid": no se
    acepta punto_id ni ningún otro campo; la tienda sale de la orden."""

    model_config = ConfigDict(extra="forbid")

    requiere_factura: bool
    nit: Optional[str] = None
    nombre_fiscal: Optional[str] = None
    direccion_fiscal: Optional[str] = None

    @model_validator(mode="after")
    def _validar(self):
        if not self.requiere_factura:
            # Sin factura los datos se ignoran y se guardan en NULL.
            self.nit = self.nombre_fiscal = self.direccion_fiscal = None
            return self
        self.nit = normalizar_nit(self.nit)
        self.nombre_fiscal = _texto_fiscal(self.nombre_fiscal, "El nombre fiscal", NOMBRE_FISCAL_MAX)
        self.direccion_fiscal = _texto_fiscal(
            self.direccion_fiscal, "La dirección fiscal", DIRECCION_FISCAL_MAX
        )
        return self
