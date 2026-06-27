"""Tests para seed data demo."""

import pytest

from foodops.db import seed
from foodops.db.models import Empresa, PuntoVenta, UserRol, Usuario


class FakeAsyncSession:
    def __init__(self, existing_empresa=None):
        self.existing_empresa = existing_empresa
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.flushed = 0
        self._next_id = 1

    async def scalar(self, _stmt):
        return self.existing_empresa

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def test_build_demo_seed_data_is_deterministic():
    data = seed.build_demo_seed_data()

    assert data["empresa"]["nit"] == seed.DEMO_EMPRESA_NIT
    assert len(data["puntos_venta"]) == 2
    assert len(data["usuarios"]) == 4
    assert {usuario["rol"] for usuario in data["usuarios"]} == {
        UserRol.ADMIN,
        UserRol.TOMADOR_ORDEN,
        UserRol.COCINERO,
        UserRol.GERENTE_PUNTO,
    }


@pytest.mark.asyncio
async def test_seed_demo_data_creates_empresa_puntos_and_users(monkeypatch):
    monkeypatch.setattr(seed, "hash_password", lambda password: f"hashed:{password}")
    db = FakeAsyncSession()

    result = await seed.seed_demo_data(db)

    empresas = [obj for obj in db.added if isinstance(obj, Empresa)]
    puntos = [obj for obj in db.added if isinstance(obj, PuntoVenta)]
    usuarios = [obj for obj in db.added if isinstance(obj, Usuario)]

    assert result.created is True
    assert result.puntos_venta == 2
    assert result.usuarios == 4
    assert len(empresas) == 1
    assert len(puntos) == 2
    assert len(usuarios) == 4
    assert usuarios[0].password_hash == "hashed:FoodOps123!"
    assert usuarios[1].punto_id == puntos[0].id
    assert db.committed is True
    assert db.rolled_back is False


@pytest.mark.asyncio
async def test_seed_demo_data_does_not_duplicate_existing_empresa():
    db = FakeAsyncSession(existing_empresa=Empresa(nit=seed.DEMO_EMPRESA_NIT))

    result = await seed.seed_demo_data(db)

    assert result.created is False
    assert result.puntos_venta == 0
    assert result.usuarios == 0
    assert db.added == []
    assert db.committed is False
