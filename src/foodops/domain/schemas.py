"""Pydantic schemas para validación"""

from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List, Any

class UsuarioCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    nombre_completo: str

class UsuarioResponse(BaseModel):
    id: int
    username: str
    email: str
    nombre_completo: str
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OrdenItemCreate(BaseModel):
    producto: str
    cantidad: int
    precio_unitario: float
    especiales: Optional[str] = None

class OrdenCreate(BaseModel):
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None
    metodo_pago: str
    items: List[OrdenItemCreate]
    es_domicilio: bool = False
    notas_especiales: Optional[str] = None
    dinero_recibido: Optional[float] = None
    vuelto: Optional[float] = None

class OrdenResponse(BaseModel):
    id: int
    numero_orden: str
    estado: str
    total: float
    created_at: datetime

    class Config:
        from_attributes = True


class ItemTransaccion(BaseModel):
    nombre: str
    cantidad: float
    unidad: str = "pieza"
    precio_unitario: float
    costo_unitario: float = 0
    subtotal: float
    tipo_pieza: Optional[str] = None


class CrearTransaccionRequest(BaseModel):
    punto_id: int
    orden_id: Optional[int] = None
    tipo_venta: str = "individual"
    nombre_iniciativa: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None
    tipo_cliente: str = "para_llevar"
    precio_venta: float
    costo_total: float = 0
    margen_bruto: float = 0
    margen_pct: float = 0
    metodo_pago: str
    items: List[ItemTransaccion]
    requerimientos_especiales: Optional[str] = None
