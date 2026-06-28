"""Pydantic schemas para validación"""

from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

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

class OrdenResponse(BaseModel):
    id: int
    numero_orden: str
    estado: str
    total: float
    created_at: datetime
    
    class Config:
        from_attributes = True
