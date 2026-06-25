"""Tests para modelos de dominio"""

import pytest
from src.foodops.domain.models import Usuario, Orden, UserRol, OrdenEstado

def test_crear_usuario():
    usuario = Usuario(id=1, username="chef1", rol=UserRol.COCINERO, punto_id=1)
    assert usuario.username == "chef1"
    assert usuario.rol == UserRol.COCINERO

def test_crear_orden():
    orden = Orden(id=1, numero="ORD-001", punto_id=1, estado=OrdenEstado.PENDIENTE)
    assert orden.numero == "ORD-001"
    assert orden.estado == OrdenEstado.PENDIENTE
