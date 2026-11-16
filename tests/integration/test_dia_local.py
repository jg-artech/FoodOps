"""Un solo "día local" (Guatemala) para el listado del vendedor y la caja.

Una orden de las 23:30 de hoy (Guatemala) es de hoy en el listado del
vendedor, al abrir caja, en el reporte de cierre y en el efectivo esperado;
una de las 00:10 de mañana es de mañana en todos. El reloj se fija con
foodops.utils.timeutils.ahora_utc, y nada depende de la zona del servidor.
"""

import time
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.api.router_caja import _calcular_efectivo_esperado
from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import (
    Empresa,
    MetodoPago,
    Orden,
    OrdenEstado,
    PuntoVenta,
    TransaccionVenta,
    Usuario,
    UserRol,
)
from foodops.db.models_caja import CajaDiaria
from foodops.utils import timeutils

HOY = date(2026, 3, 10)
MANANA = HOY + timedelta(days=1)
# Guatemala = UTC-6: 23:30 de HOY y 00:10 de MAÑANA, en UTC naive.
UTC_2330_HOY = datetime(2026, 3, 11, 5, 30)
UTC_0010_MANANA = datetime(2026, 3, 11, 6, 10)
# Relojes: 23:45 de HOY y 00:20 de MAÑANA en Guatemala.
RELOJ_HOY = datetime(2026, 3, 11, 5, 45)
RELOJ_MANANA = datetime(2026, 3, 11, 6, 20)


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture
def reloj(monkeypatch):
    def fijar(ahora):
        monkeypatch.setattr(timeutils, "ahora_utc", lambda: ahora)
    return fijar


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def datos(S):
    s = S()
    e = Empresa(nombre="Dia local Test", nit=f"TEST-DL-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda dia local {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()

    out = {"punto": p.id}
    for clave, rol in [("vendedor", UserRol.TOMADOR_ORDEN), ("resp", UserRol.RESP_TIENDA)]:
        u = Usuario(empresa_id=e.id, punto_id=p.id, username=f"dl_{uuid.uuid4().hex[:10]}",
                    email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=hash_password("x"), rol=rol)
        s.add(u)
        s.flush()
        out[clave] = {"user_id": u.id, "username": u.username, "punto_id": p.id,
                      "rol": u.rol.value, "empresa_id": e.id}

    # Dos ventas en efectivo cobradas, a cada lado de la medianoche local.
    for clave, creada, monto in [("2330", UTC_2330_HOY, 100), ("0010", UTC_0010_MANANA, 7)]:
        o = Orden(punto_id=p.id, numero_orden=f"DL-{clave}-{uuid.uuid4().hex[:8]}",
                  metodo_pago=MetodoPago.EFECTIVO, total=monto, estado=OrdenEstado.ENTREGADO,
                  estado_cobro="cobrada", cliente_nombre="Cliente", created_at=creada,
                  tomada_por=out["vendedor"]["user_id"])
        s.add(o)
        s.flush()
        s.add(TransaccionVenta(punto_id=p.id, orden_id=o.id, precio_venta=monto,
                               metodo_pago="efectivo", estado="completada", created_at=creada))
        out[f"orden_{clave}"] = o.id
    s.commit()
    s.close()
    return out


def _ids_vendedor(api, datos):
    r = api.get("/api/ordenes/", headers=_auth(datos["vendedor"]))
    assert r.status_code == 200, r.text
    return {o["id"] for o in r.json()}


def _abrir_caja(api, datos, S):
    r = api.post("/api/caja/abrir", json={"fondo_inicial": 500}, headers=_auth(datos["resp"]))
    assert r.status_code == 200, r.text
    s = S()
    try:
        return s.execute(
            select(CajaDiaria).where(CajaDiaria.punto_id == datos["punto"])
            .order_by(CajaDiaria.id.desc())
        ).scalars().first().fecha
    finally:
        s.close()


def _ventas_cierre(api, datos, fecha):
    r = api.get("/api/caja/reporte-cierre", params={"fecha": fecha.isoformat()},
                headers=_auth(datos["resp"]))
    assert r.status_code == 200, r.text
    return r.json()["resumen"]["total_ventas"]


def _efectivo_esperado(S, datos, fecha):
    s = S()
    try:
        caja = s.execute(select(CajaDiaria).where(
            CajaDiaria.punto_id == datos["punto"], CajaDiaria.fecha == fecha)).scalars().one()
        return float(_calcular_efectivo_esperado(s, caja)) - float(caja.fondo_inicial)
    finally:
        s.close()


def test_23_30_es_de_hoy_y_00_10_de_manana_en_listado_y_caja(api, datos, S, reloj):
    # 23:45 de HOY en Guatemala (ya es día siguiente en UTC).
    reloj(RELOJ_HOY)
    vistas = _ids_vendedor(api, datos)
    assert datos["orden_2330"] in vistas
    assert datos["orden_0010"] not in vistas
    assert _abrir_caja(api, datos, S) == HOY

    # 00:20 de MAÑANA.
    reloj(RELOJ_MANANA)
    vistas = _ids_vendedor(api, datos)
    assert datos["orden_0010"] in vistas
    assert datos["orden_2330"] not in vistas
    assert _abrir_caja(api, datos, S) == MANANA

    # Cierre de caja: cada venta cae en su día local.
    assert _ventas_cierre(api, datos, HOY) == 100
    assert _ventas_cierre(api, datos, MANANA) == 7
    assert _efectivo_esperado(S, datos, HOY) == 100
    assert _efectivo_esperado(S, datos, MANANA) == 7


def test_listado_y_caja_usan_los_mismos_limites():
    assert timeutils.limites_hoy_guatemala(RELOJ_HOY) == timeutils.local_day_bounds(HOY)
    inicio, fin = timeutils.local_day_bounds(HOY)
    assert inicio <= UTC_2330_HOY < fin
    assert not (inicio <= UTC_0010_MANANA < fin)


@pytest.mark.parametrize("tz", ["UTC", "America/Guatemala", "Asia/Tokyo"])
def test_el_dia_local_no_depende_de_la_zona_del_servidor(monkeypatch, tz):
    monkeypatch.setenv("TZ", tz)
    time.tzset()
    try:
        assert timeutils.hoy_local(RELOJ_HOY) == HOY
        assert timeutils.hoy_local(RELOJ_MANANA) == MANANA
        assert timeutils.local_day_bounds(HOY) == (datetime(2026, 3, 10, 6), datetime(2026, 3, 11, 6))
    finally:
        monkeypatch.undo()
        time.tzset()
