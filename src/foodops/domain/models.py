"""Domain models para FoodOps"""

from enum import Enum
from typing import Optional
from datetime import datetime

class UserRol(str, Enum):
    ADMIN = "admin"
    GERENTE_PUNTO = "gerente_punto"
    TOMADOR_ORDEN = "tomador_orden"
    COCINERO = "cocinero"
    BODEGUERO = "bodeguero"

class OrdenEstado(str, Enum):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    LISTO = "listo"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"

class MetodoPago(str, Enum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"

# Modelos de dominio (sin BD)
class Usuario:
    def __init__(self, id: int, username: str, rol: UserRol, punto_id: int):
        self.id = id
        self.username = username
        self.rol = rol
        self.punto_id = punto_id

class Orden:
    def __init__(self, id: int, numero: str, punto_id: int, estado: OrdenEstado):
        self.id = id
        self.numero = numero
        self.punto_id = punto_id
        self.estado = estado
        self.items = []
        self.created_at = datetime.utcnow()
