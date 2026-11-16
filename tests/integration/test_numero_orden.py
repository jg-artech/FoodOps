"""numero_orden único por tienda sin cambiar el formato visible.

El número es ORD-{punto}-{AAAAMMDDhhmmss}. Si otra orden de la misma tienda
ya tiene ese número (mismo segundo), crear_orden reintenta con -2 ... -9
dentro de un SAVEPOINT. Las órdenes normales conservan el número sin sufijo.
Agotados los intentos: 409 con mensaje fijo, sin SQL.

El reloj del router se fija con monkeypatch para forzar el mismo segundo.
"""

import threading
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.api import router_ordenes
from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import AuditLog, Empresa, MetodoPago, Orden, OrdenEstado, PuntoVenta, Usuario, UserRol

_HASH = hash_password("Clave-numero-1")
_INSTANTE = datetime(2026, 11, 16, 14, 30, 5)


class _RelojFijo(datetime):
    @classmethod
    def utcnow(cls):
        return _INSTANTE


@pytest.fixture
def reloj_fijo(monkeypatch):
    monkeypatch.setattr(router_ordenes, "datetime", _RelojFijo)


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def tienda(S):
    """Tienda nueva por prueba, con dos vendedores."""
    s = S()
    e = Empresa(nombre="Numero Orden Test", nit=f"TEST-NO-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda NO {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()
    vendedores = []
    for _ in range(2):
        u = Usuario(
            empresa_id=e.id, punto_id=p.id, username=f"no_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=UserRol.TOMADOR_ORDEN,
        )
        s.add(u)
        s.flush()
        vendedores.append({"user_id": u.id, "username": u.username, "punto_id": p.id,
                           "rol": u.rol.value, "empresa_id": e.id})
    s.commit()
    out = {"id": p.id, "vendedores": vendedores, "base": f"ORD-{p.id}-{_INSTANTE:%Y%m%d%H%M%S}"}
    s.close()
    return out


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


_BODY = {
    "cliente_nombre": "Cliente número",
    "metodo_pago": "tarjeta",
    "es_domicilio": False,
    "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 45.5}],
}


def _crear(api, usuario):
    return api.post("/api/ordenes/", json=_BODY, headers=_auth(usuario))


def test_dos_ordenes_mismo_segundo_misma_tienda(api, tienda, reloj_fijo, S):
    r1 = _crear(api, tienda["vendedores"][0])
    r2 = _crear(api, tienda["vendedores"][1])
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    # La primera conserva el formato visible de siempre; la segunda lleva sufijo.
    assert r1.json()["numero_orden"] == tienda["base"]
    assert r2.json()["numero_orden"] == f"{tienda['base']}-2"

    # La auditoría registra el número definitivo, una sola vez por orden.
    s = S()
    try:
        numeros = [
            a.detalle["numero_orden"]
            for a in s.execute(
                select(AuditLog).where(
                    AuditLog.accion == "CREAR_ORDEN",
                    AuditLog.entidad_id.in_([str(r1.json()["id"]), str(r2.json()["id"])]),
                )
            ).scalars()
        ]
    finally:
        s.close()
    assert sorted(numeros) == sorted([tienda["base"], f"{tienda['base']}-2"])


def test_dos_ordenes_simultaneas_misma_tienda(api, tienda, reloj_fijo):
    """Dos peticiones en paralelo: la segunda espera el commit de la primera
    en el índice único, choca y reintenta con sufijo. Ninguna da 400 ni 500."""
    barrera = threading.Barrier(2)
    respuestas = [None, None]

    def crear(i):
        barrera.wait()
        respuestas[i] = _crear(api, tienda["vendedores"][i])

    hilos = [threading.Thread(target=crear, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    codigos = [r.status_code for r in respuestas]
    assert codigos == [200, 200], [r.text for r in respuestas]
    numeros = {r.json()["numero_orden"] for r in respuestas}
    assert numeros == {tienda["base"], f"{tienda['base']}-2"}


def test_otra_tienda_mismo_segundo_no_lleva_sufijo(api, tienda, reloj_fijo, S):
    _crear(api, tienda["vendedores"][0])
    s = S()
    p = PuntoVenta(empresa_id=tienda["vendedores"][0]["empresa_id"], nombre=f"Otra NO {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()
    u = Usuario(
        empresa_id=p.empresa_id, punto_id=p.id, username=f"no_{uuid.uuid4().hex[:10]}",
        email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=UserRol.TOMADOR_ORDEN,
    )
    s.add(u)
    s.commit()
    otro = {"user_id": u.id, "username": u.username, "punto_id": p.id, "rol": u.rol.value,
            "empresa_id": p.empresa_id}
    pid = p.id
    s.close()

    r = _crear(api, otro)
    assert r.status_code == 200, r.text
    assert r.json()["numero_orden"] == f"ORD-{pid}-{_INSTANTE:%Y%m%d%H%M%S}"


def test_intentos_agotados_dan_409_sin_sql(api, tienda, reloj_fijo, S):
    base = tienda["base"]
    s = S()
    for numero in [base] + [f"{base}-{n}" for n in range(2, 10)]:
        s.add(Orden(punto_id=tienda["id"], numero_orden=numero, metodo_pago=MetodoPago.TARJETA,
                    total=1, estado=OrdenEstado.PENDIENTE, estado_cobro="cobrada"))
    s.commit()
    antes = s.query(Orden).filter(Orden.punto_id == tienda["id"]).count()
    s.close()

    r = _crear(api, tienda["vendedores"][0])
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert detalle == "No se pudo asignar un número de orden único. Intenta de nuevo."
    for palabra in ("INSERT", "UNIQUE", "uq_ordenes", "psycopg", "SQL", "DETAIL"):
        assert palabra not in detalle

    s = S()
    assert s.query(Orden).filter(Orden.punto_id == tienda["id"]).count() == antes
    s.close()
