"""Flujo de cobro en efectivo: PENDIENTE_RECIBIR -> COBRADA.

Ver docs/AUDITORIA_COBRO_EFECTIVO.md. Los usuarios y órdenes viven solo en
la BD de prueba; la de desarrollo no se toca.

Nota de diseño de estos tests: numero_orden se genera con resolución de
segundos (ORD-{punto}-{YYYYMMDDHHMMSS}, ver crear_orden en
router_ordenes.py) - una limitación preexistente, no algo que esta tarea
pidiera tocar. Crear varias órdenes por el endpoint real en la misma
tienda en el mismo segundo choca con uq_ordenes_punto_numero. Por eso el
setup de la mayoría de los tests inserta la orden directo en la BD (con un
numero_orden único por UUID) y solo usa POST /api/ordenes/ real en los dos
tests que validan específicamente la lógica de creación, cada uno en su
propia tienda para no competir entre sí.
"""

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import Empresa, MetodoPago, Orden, OrdenEstado, PuntoVenta, Usuario, UserRol


def _auth(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


@pytest.fixture(scope="module")
def datos(engine):
    """Dos tiendas (la segunda solo para no competir por numero_orden con la
    primera en el test de creación con tarjeta) + un vendedor y un
    responsable en la tienda principal."""
    Session = sessionmaker(bind=engine)
    s = Session()

    empresa = Empresa(nombre="Cobro Efectivo Test", nit="TEST-CE-1")
    s.add(empresa)
    s.flush()

    tienda = PuntoVenta(empresa_id=empresa.id, nombre="Tienda CE")
    tienda2 = PuntoVenta(empresa_id=empresa.id, nombre="Tienda CE 2")
    s.add_all([tienda, tienda2])
    s.flush()

    def usuario(username, rol, punto):
        u = Usuario(
            empresa_id=empresa.id,
            punto_id=punto.id,
            username=username,
            email=f"{username}@test.gt",
            password_hash=hash_password("secreta123"),
            rol=rol,
        )
        s.add(u)
        return u

    vendedor = usuario("ce_vendedor", UserRol.TOMADOR_ORDEN, tienda)
    responsable = usuario("ce_responsable", UserRol.RESP_TIENDA, tienda)
    vendedor2 = usuario("ce_vendedor2", UserRol.TOMADOR_ORDEN, tienda2)
    s.commit()

    def credenciales(u: Usuario) -> dict:
        return {
            "user_id": u.id,
            "username": u.username,
            "punto_id": u.punto_id,
            "rol": u.rol.value,
            "empresa_id": u.empresa_id,
        }

    out = {
        "tienda": tienda.id,
        "tienda2": tienda2.id,
        "vendedor": credenciales(vendedor),
        "responsable": credenciales(responsable),
        "vendedor2": credenciales(vendedor2),
    }
    s.close()
    yield out


def _insertar_orden(
    engine,
    punto_id,
    *,
    metodo_pago=MetodoPago.EFECTIVO,
    estado_cobro="pendiente_recibir",
    estado=OrdenEstado.PENDIENTE,
    total=100.0,
    dinero_recibido=None,
    vuelto=None,
    tomada_por=None,
) -> int:
    """Inserta una Orden directo en la BD (no por el endpoint real) con un
    numero_orden único por UUID - evita la colisión de uq_ordenes_punto_numero
    al crear varias órdenes de prueba en el mismo segundo (ver docstring del
    módulo)."""
    Session = sessionmaker(bind=engine)
    s = Session()
    o = Orden(
        punto_id=punto_id,
        numero_orden=f"TEST-{uuid.uuid4().hex[:12]}",
        metodo_pago=metodo_pago,
        total=total,
        dinero_recibido=dinero_recibido,
        vuelto=vuelto,
        estado=estado,
        estado_cobro=estado_cobro,
        tomada_por=tomada_por,
    )
    s.add(o)
    s.commit()
    orden_id = o.id
    s.close()
    return orden_id


# ---------------------------------------------------------------------------
# Creación real vía POST /api/ordenes/: estado_cobro según metodo_pago
# ---------------------------------------------------------------------------


def test_orden_en_efectivo_nace_pendiente_recibir(api, datos):
    r = api.post(
        "/api/ordenes/",
        json={
            "metodo_pago": "efectivo",
            "dinero_recibido": 100,
            "vuelto": 0,
            "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 100}],
        },
        headers=_auth(datos["vendedor"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado_cobro"] == "pendiente_recibir"
    # El estado de cocina no se toca - sigue siendo el de siempre.
    assert body["estado"] == "pendiente"


def test_orden_con_tarjeta_nace_cobrada(api, datos):
    # Tienda distinta a la del test anterior: ambos pegan al endpoint real,
    # que genera numero_orden con resolución de segundos - en tiendas
    # distintas no compiten por la misma clave única.
    r = api.post(
        "/api/ordenes/",
        json={
            "metodo_pago": "tarjeta",
            "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 100}],
        },
        headers=_auth(datos["vendedor2"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado_cobro"] == "cobrada"


# ---------------------------------------------------------------------------
# Cancelación: vendedor puede cancelar pendiente, no puede cancelar cobrada
# ---------------------------------------------------------------------------


def test_vendedor_cancela_orden_pendiente_ok(api, datos, engine):
    orden_id = _insertar_orden(engine, datos["tienda"], estado_cobro="pendiente_recibir")
    r = api.put(
        f"/api/ordenes/{orden_id}/status",
        json={"estado": "cancelado"},
        headers=_auth(datos["vendedor"]),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "cancelado"


def test_vendedor_no_puede_cancelar_orden_cobrada(api, datos, engine):
    orden_id = _insertar_orden(engine, datos["tienda"], estado_cobro="cobrada")
    r = api.put(
        f"/api/ordenes/{orden_id}/status",
        json={"estado": "cancelado"},
        headers=_auth(datos["vendedor"]),
    )
    assert r.status_code == 403


def test_responsable_si_puede_cancelar_orden_cobrada(api, datos, engine):
    """No estaba en la lista mínima pedida, pero es consecuencia directa de
    la regla ("el vendedor no puede") - gerencia/responsable conservan la
    autoridad de anular incluso una venta ya cobrada (ej. reclamo de
    cliente), verificado explícitamente para no dejarlo como supuesto."""
    orden_id = _insertar_orden(engine, datos["tienda"], estado_cobro="cobrada")
    r = api.put(
        f"/api/ordenes/{orden_id}/status",
        json={"estado": "cancelado"},
        headers=_auth(datos["responsable"]),
    )
    assert r.status_code == 200


def test_cancelar_orden_con_tarjeta_sigue_sin_restriccion_nueva(api, datos, engine):
    """El candado nuevo es solo para efectivo: una orden con tarjeta nace
    "cobrada" de inmediato (no hay entrega física de efectivo que esperar),
    y el vendedor debe poder seguir cancelándola como antes."""
    orden_id = _insertar_orden(
        engine, datos["tienda"], metodo_pago=MetodoPago.TARJETA, estado_cobro="cobrada"
    )
    r = api.put(
        f"/api/ordenes/{orden_id}/status",
        json={"estado": "cancelado"},
        headers=_auth(datos["vendedor"]),
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Confirmar cobro
# ---------------------------------------------------------------------------


def test_responsable_confirma_cobro_y_pasa_a_cobrada(api, datos, engine):
    orden_id = _insertar_orden(
        engine, datos["tienda"], estado_cobro="pendiente_recibir", total=85, dinero_recibido=100, vuelto=15
    )
    r = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 15},
        headers=_auth(datos["responsable"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["estado_cobro"] == "cobrada"
    assert body["monto_recibido"] == 100
    assert body["vuelto_entregado"] == 15
    assert body["confirmado_por"] == datos["responsable"]["user_id"]
    assert body["confirmado_at"] is not None


def test_responsable_confirma_con_montos_distintos_al_esperado(api, datos, engine):
    """dinero_recibido/vuelto (estimado del vendedor) y monto_recibido/
    vuelto_entregado (confirmado por el responsable) son independientes -
    el billete real que llegó puede no ser el que se estimó al crear la
    orden."""
    orden_id = _insertar_orden(
        engine, datos["tienda"], estado_cobro="pendiente_recibir", total=85, dinero_recibido=100, vuelto=15
    )
    r = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 200, "vuelto_entregado": 115},  # llegó un billete distinto
        headers=_auth(datos["responsable"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["monto_recibido"] == 200
    assert body["vuelto_entregado"] == 115
    assert body["vuelto"] == 15  # el campo estimado del vendedor no se tocó


def test_tomador_orden_no_puede_confirmar_cobro(api, datos, engine):
    orden_id = _insertar_orden(engine, datos["tienda"], estado_cobro="pendiente_recibir")
    r = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(datos["vendedor"]),
    )
    assert r.status_code == 403


def test_no_se_puede_confirmar_cobro_dos_veces(api, datos, engine):
    orden_id = _insertar_orden(engine, datos["tienda"], estado_cobro="pendiente_recibir")
    r1 = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(datos["responsable"]),
    )
    assert r1.status_code == 200
    r2 = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(datos["responsable"]),
    )
    assert r2.status_code == 400


def test_no_se_puede_confirmar_cobro_de_orden_cancelada(api, datos, engine):
    orden_id = _insertar_orden(
        engine, datos["tienda"], estado_cobro="pendiente_recibir", estado=OrdenEstado.CANCELADO
    )
    r = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(datos["responsable"]),
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Cierre de caja bloqueado con pendientes - tienda propia, aislada del resto
# (abre/cierra su propia CajaDiaria).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tienda_cierre(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    empresa = Empresa(nombre="Cierre Caja Test", nit="TEST-CE-2")
    s.add(empresa)
    s.flush()
    tienda = PuntoVenta(empresa_id=empresa.id, nombre="Tienda Cierre")
    s.add(tienda)
    s.flush()
    responsable = Usuario(
        empresa_id=empresa.id,
        punto_id=tienda.id,
        username="ce_cierre_responsable",
        email="ce_cierre_responsable@test.gt",
        password_hash=hash_password("secreta123"),
        rol=UserRol.RESP_TIENDA,
    )
    s.add(responsable)
    s.commit()
    out = {
        "tienda": tienda.id,
        "responsable": {
            "user_id": responsable.id,
            "username": responsable.username,
            "punto_id": responsable.punto_id,
            "rol": responsable.rol.value,
            "empresa_id": responsable.empresa_id,
        },
    }
    s.close()
    yield out


def test_no_se_puede_cerrar_caja_con_orden_pendiente_recibir(api, tienda_cierre, engine):
    resp = tienda_cierre["responsable"]
    r = api.post("/api/caja/abrir", json={"fondo_inicial": 500}, headers=_auth(resp))
    assert r.status_code == 200, r.text

    _insertar_orden(engine, tienda_cierre["tienda"], estado_cobro="pendiente_recibir", total=50)

    r = api.post("/api/caja/cerrar", json={"efectivo_contado": 500}, headers=_auth(resp))
    assert r.status_code == 400
    assert "sin confirmar el cobro" in r.json()["detail"]


# ---------------------------------------------------------------------------
# _calcular_efectivo_esperado: solo cuenta efectivo COBRADA y no cancelada
# ---------------------------------------------------------------------------


def test_cuadre_no_incluye_ventas_pendientes_ni_canceladas(engine, datos):
    """Unit test directo de _calcular_efectivo_esperado (no vía HTTP): crea
    tres transacciones en efectivo con sus respectivas órdenes en los tres
    estados relevantes y confirma que solo la COBRADA-no-cancelada suma."""
    from foodops.api.router_caja import _calcular_efectivo_esperado
    from foodops.db.models import TransaccionVenta
    from foodops.db.models_caja import CajaDiaria

    Session = sessionmaker(bind=engine)
    s = Session()
    punto_id = datos["tienda2"]  # tienda sin otras ventas en efectivo, para un cuadre predecible

    def orden_con_venta(estado_cobro, estado, monto):
        o = Orden(
            punto_id=punto_id,
            numero_orden=f"TEST-{uuid.uuid4().hex[:12]}",
            metodo_pago=MetodoPago.EFECTIVO,
            total=monto,
            estado=estado,
            estado_cobro=estado_cobro,
        )
        s.add(o)
        s.flush()
        t = TransaccionVenta(
            punto_id=punto_id,
            orden_id=o.id,
            metodo_pago="efectivo",
            precio_venta=monto,
        )
        s.add(t)

    orden_con_venta("cobrada", OrdenEstado.ENTREGADO, 100.0)
    orden_con_venta("pendiente_recibir", OrdenEstado.PENDIENTE, 200.0)
    # cobrada y luego anulada por gerencia (ver
    # test_responsable_si_puede_cancelar_orden_cobrada) - no debe contar.
    orden_con_venta("cobrada", OrdenEstado.CANCELADO, 300.0)
    s.commit()

    caja = CajaDiaria(
        punto_id=punto_id,
        fecha=date.today(),
        fondo_inicial=0,
        estado="abierta",
        abierta_por=datos["responsable"]["user_id"],
    )
    s.add(caja)
    s.commit()

    esperado = _calcular_efectivo_esperado(s, caja)
    assert esperado == 100

    s.close()
