"""Cargo de entrega en órdenes a domicilio (migración 014).

Cubre: validaciones del cargo (solo domicilio, uno por orden, >= 0, dos
decimales), tope por tienda, autorización de un responsable con token de un
solo uso atado a tienda/monto/responsable, total y cuadre calculados en el
servidor, auditoría con antes/después y el tope editable solo por gerencia.

numero_orden tiene resolución de segundos y es único por tienda: dos órdenes
por el endpoint real en la misma tienda y el mismo segundo chocan. Por eso
cada prueba que crea órdenes pide su propia tienda (fixture `tienda`).
"""

import time
import uuid
from datetime import date, datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.api.router_ordenes import _ROLES_CONFIRMAR_COBRO
from foodops.core.auth import create_access_token, hash_password
from foodops.core.config import settings
from foodops.db.models import (
    AuditLog,
    AutorizacionCargoUsada,
    Empresa,
    Orden,
    OrdenItem,
    PuntoVenta,
    TransaccionVenta,
    Usuario,
    UserRol,
)
from foodops.domain import autorizacion_cargo as ac

CLAVE = "Clave-prueba-1"
_HASH = hash_password(CLAVE)  # una sola vez: bcrypt es lento


def _auth(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def empresa_id(S):
    s = S()
    e = Empresa(nombre="Cargo Entrega Test", nit=f"TEST-CE-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.commit()
    eid = e.id
    s.close()
    return eid


def _usuario(s, empresa_id, rol, punto_id, prefijo="ce"):
    u = Usuario(
        empresa_id=empresa_id,
        punto_id=punto_id,
        username=f"{prefijo}_{uuid.uuid4().hex[:10]}",
        email=f"{uuid.uuid4().hex[:10]}@test.gt",
        password_hash=_HASH,
        rol=rol,
    )
    s.add(u)
    s.flush()
    return u


def _cred(u: Usuario) -> dict:
    return {
        "user_id": u.id,
        "username": u.username,
        "punto_id": u.punto_id,
        "rol": u.rol.value,
        "empresa_id": u.empresa_id,
    }


@pytest.fixture
def tienda(S, empresa_id):
    """Tienda nueva por prueba, con tope 200.00, un vendedor y un responsable."""
    s = S()
    p = PuntoVenta(empresa_id=empresa_id, nombre=f"Tienda CE {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()
    vendedor = _usuario(s, empresa_id, UserRol.TOMADOR_ORDEN, p.id)
    resp = _usuario(s, empresa_id, UserRol.RESP_TIENDA, p.id)
    s.commit()
    out = {
        "id": p.id,
        "empresa_id": empresa_id,
        "vendedor": _cred(vendedor),
        "resp": _cred(resp),
        "resp_username": resp.username,
    }
    s.close()
    return out


def _orden(cargo=None, *, domicilio=True, metodo="tarjeta", autorizacion=None, extra_cargo=None, items=None):
    body = {
        "cliente_nombre": "Cliente entrega",
        "metodo_pago": metodo,
        "es_domicilio": domicilio,
        "cliente_telefono": "5555-0000" if domicilio else None,
        "cliente_direccion": "Zona 1" if domicilio else None,
        "items": items if items is not None else [
            {"producto": "1/4 Pollo", "cantidad": 2, "precio_unitario": 45.5},
        ],
    }
    if cargo is not None:
        body["items"].append({"producto": "Envío", "cantidad": 1, "precio_unitario": cargo,
                              "tipo": "entrega", **(extra_cargo or {})})
    if autorizacion is not None:
        body["autorizacion_cargo"] = autorizacion
    return body


def _crear(api, usuario, body):
    return api.post("/api/ordenes/", json=body, headers=_auth(usuario))


def _autorizar(api, tienda_, monto, *, username=None, password=CLAVE, quien=None):
    return api.post(
        "/api/auth/autorizar-cargo-entrega",
        json={"username": username or tienda_["resp_username"], "password": password, "monto": monto},
        headers=_auth(quien or tienda_["vendedor"]),
    )


def _token(api, tienda_, monto, **kw):
    r = _autorizar(api, tienda_, monto, **kw)
    assert r.status_code == 200, r.text
    return r.json()["autorizacion_cargo"]


def _ordenes_de(S, punto_id):
    s = S()
    try:
        return s.execute(select(Orden).where(Orden.punto_id == punto_id)).scalars().all()
    finally:
        s.close()


def _auditoria(S, accion, **filtros):
    s = S()
    try:
        q = select(AuditLog).where(AuditLog.accion == accion)
        for campo, valor in filtros.items():
            q = q.where(getattr(AuditLog, campo) == valor)
        return s.execute(q.order_by(AuditLog.id)).scalars().all()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


def test_roles_que_autorizan_son_los_que_confirman_cobro():
    assert set(ac.ROLES_AUTORIZAN_CARGO) == set(_ROLES_CONFIRMAR_COBRO)


# ---------------------------------------------------------------------------
# Validaciones del cargo
# ---------------------------------------------------------------------------


def test_cargo_en_orden_no_domicilio_da_422(api, tienda, S):
    r = _crear(api, tienda["vendedor"], _orden(25, domicilio=False))
    assert r.status_code == 422, r.text
    assert "solo aplica a órdenes a domicilio" in r.json()["detail"][0]["msg"]
    assert _ordenes_de(S, tienda["id"]) == []


def test_dos_cargos_en_la_misma_orden_dan_422(api, tienda):
    body = _orden(25)
    body["items"].append({"producto": "x", "cantidad": 1, "precio_unitario": 10, "tipo": "entrega"})
    r = _crear(api, tienda["vendedor"], body)
    assert r.status_code == 422
    assert "un cargo de entrega" in r.json()["detail"][0]["msg"]


@pytest.mark.parametrize("monto", [-1, -0.01, "10.005", 10.123], ids=["neg", "neg-centavo", "3-dec-str", "3-dec"])
def test_monto_negativo_o_con_tres_decimales_da_422(api, tienda, monto):
    assert _crear(api, tienda["vendedor"], _orden(monto)).status_code == 422


def test_tipo_desconocido_da_422(api, tienda):
    body = _orden()
    body["items"][0]["tipo"] = "descuento"
    assert _crear(api, tienda["vendedor"], body).status_code == 422


# ---------------------------------------------------------------------------
# Dentro del tope
# ---------------------------------------------------------------------------


def test_cargo_dentro_del_tope_suma_al_total_calculado_en_servidor(api, tienda, S):
    # El cliente intenta poner otro nombre y otra cantidad al cargo: el
    # servidor los fija ("Cargo de entrega", 1). No hay campo total en el body.
    body = _orden(25.75, extra_cargo={"producto": "Regalo", "cantidad": 3})
    body["total"] = 1  # ignorado: OrdenCreate no tiene total
    r = _crear(api, tienda["vendedor"], body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == pytest.approx(2 * 45.5 + 25.75)
    cargo = [i for i in data["items"] if i["tipo"] == "entrega"]
    assert cargo == [{
        "producto": "Cargo de entrega", "cantidad": 1, "precio_unitario": 25.75,
        "subtotal": 25.75, "especiales": None, "tipo": "entrega",
    }]
    assert [i["tipo"] for i in data["items"]].count("producto") == 1

    s = S()
    fila = s.execute(select(OrdenItem).where(OrdenItem.orden_id == data["id"],
                                             OrdenItem.tipo == "entrega")).scalar_one()
    s.close()
    assert (fila.producto, fila.cantidad, fila.subtotal) == ("Cargo de entrega", 1, 25.75)


def test_cargo_igual_al_tope_no_pide_autorizacion(api, tienda):
    assert _crear(api, tienda["vendedor"], _orden(200)).status_code == 200


def test_cargo_cero_es_valido(api, tienda):
    r = _crear(api, tienda["vendedor"], _orden(0))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == pytest.approx(91)


def test_orden_sin_cargo_sigue_igual(api, tienda):
    r = _crear(api, tienda["vendedor"], _orden())
    assert r.status_code == 200
    assert {i["tipo"] for i in r.json()["items"]} == {"producto"}


def test_token_enviado_sin_necesidad_no_se_consume(api, tienda, S):
    token = _token(api, tienda, 50)
    assert _crear(api, tienda["vendedor"], _orden(50, autorizacion=token)).status_code == 200
    s = S()
    assert s.execute(select(AutorizacionCargoUsada).where(
        AutorizacionCargoUsada.punto_id == tienda["id"])).first() is None
    s.close()


# ---------------------------------------------------------------------------
# Sobre el tope
# ---------------------------------------------------------------------------


def test_sobre_el_tope_sin_autorizacion_da_403_y_no_crea_la_orden(api, tienda, S):
    r = _crear(api, tienda["vendedor"], _orden(200.01))
    assert r.status_code == 403
    assert "requiere autorización de un responsable" in r.json()["detail"]
    assert _ordenes_de(S, tienda["id"]) == []


def test_sobre_el_tope_creada_por_responsable_no_pide_token(api, tienda, S):
    r = _crear(api, tienda["resp"], _orden(250))
    assert r.status_code == 200, r.text
    log = _auditoria(S, "CARGO_ENTREGA_REGISTRADO", entidad_id=str(r.json()["id"]))
    assert log[0].detalle["autorizado_por"] == tienda["resp"]["user_id"]


def test_sobre_el_tope_con_autorizacion_valida_da_200(api, tienda, S):
    token = _token(api, tienda, 250)
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=token))
    assert r.status_code == 200, r.text
    orden_id = r.json()["id"]
    assert r.json()["total"] == pytest.approx(91 + 250)

    s = S()
    usada = s.execute(select(AutorizacionCargoUsada).where(
        AutorizacionCargoUsada.orden_id == orden_id)).scalar_one()
    s.close()
    assert usada.autorizado_por == tienda["resp"]["user_id"]
    assert usada.usado_por == tienda["vendedor"]["user_id"]
    assert str(usada.monto) == "250.00"


def test_auditoria_del_cargo_con_antes_despues_tope_y_autorizador(api, tienda, S):
    token = _token(api, tienda, 250)
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=token))
    orden_id = r.json()["id"]
    logs = _auditoria(S, "CARGO_ENTREGA_REGISTRADO", entidad_id=str(orden_id))
    assert len(logs) == 1
    log = logs[0]
    assert log.usuario_id == tienda["vendedor"]["user_id"]
    assert log.punto_id == tienda["id"]
    assert log.created_at is not None
    assert log.detalle["antes"] == {"monto": None}
    assert log.detalle["despues"] == {"monto": "250.00"}
    assert log.detalle["tope_vigente"] == "200.00"
    assert log.detalle["sobre_tope"] is True
    assert log.detalle["autorizado_por"] == tienda["resp"]["user_id"]


def test_auditoria_de_cargo_dentro_del_tope(api, tienda, S):
    r = _crear(api, tienda["vendedor"], _orden(30))
    log = _auditoria(S, "CARGO_ENTREGA_REGISTRADO", entidad_id=str(r.json()["id"]))[0]
    assert log.detalle["despues"] == {"monto": "30.00"}
    assert log.detalle["sobre_tope"] is False
    assert log.detalle["autorizado_por"] is None


def test_token_no_se_puede_reusar(api, tienda, S):
    token = _token(api, tienda, 250)
    assert _crear(api, tienda["vendedor"], _orden(250, autorizacion=token)).status_code == 200
    # El token está atado a esta tienda, así que la segunda orden tiene que
    # ser de la misma: se espera al siguiente segundo para que no choque por
    # numero_orden (resolución de segundos, ver docstring del módulo).
    time.sleep(1.1)
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=token))
    assert r.status_code == 403
    assert "ya fue usada" in r.json()["detail"]
    assert len(_ordenes_de(S, tienda["id"])) == 1


def test_token_con_otro_monto_da_403_y_no_se_gasta(api, tienda, S):
    token = _token(api, tienda, 250)
    r = _crear(api, tienda["vendedor"], _orden(260, autorizacion=token))
    assert r.status_code == 403
    assert "no coincide" in r.json()["detail"]
    assert _ordenes_de(S, tienda["id"]) == []
    # Rechazado, no gastado: con el monto correcto todavía sirve.
    assert _crear(api, tienda["vendedor"], _orden(250, autorizacion=token)).status_code == 200


def test_token_de_otra_tienda_da_403(api, S, empresa_id):
    """El responsable de la tienda B autoriza para un vendedor de B; un
    vendedor de la tienda A intenta usar ese token en su orden."""
    s = S()
    a = PuntoVenta(empresa_id=empresa_id, nombre=f"CE A {uuid.uuid4().hex[:6]}")
    b = PuntoVenta(empresa_id=empresa_id, nombre=f"CE B {uuid.uuid4().hex[:6]}")
    s.add_all([a, b])
    s.flush()
    vend_a = _cred(_usuario(s, empresa_id, UserRol.TOMADOR_ORDEN, a.id))
    vend_b = _cred(_usuario(s, empresa_id, UserRol.TOMADOR_ORDEN, b.id))
    resp_b = _usuario(s, empresa_id, UserRol.RESP_TIENDA, b.id)
    s.commit()
    tienda_b = {"vendedor": vend_b, "resp_username": resp_b.username}
    a_id = a.id
    s.close()

    token = _token(api, tienda_b, 250)
    r = _crear(api, vend_a, _orden(250, autorizacion=token))
    assert r.status_code == 403
    assert "otra tienda" in r.json()["detail"]
    assert _ordenes_de(S, a_id) == []


def test_token_vencido_da_403(api, tienda):
    ahora = datetime.utcnow()
    vencido = jwt.encode(
        {"typ": ac.TYP, "jti": uuid.uuid4().hex, "sub": str(tienda["resp"]["user_id"]),
         "punto_id": tienda["id"], "monto": "250.00", "solicitado_por": tienda["vendedor"]["user_id"],
         "iat": ahora - timedelta(minutes=10), "exp": ahora - timedelta(minutes=5)},
        ac._clave(), algorithm=settings.ALGORITHM,
    )
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=vencido))
    assert r.status_code == 403
    assert "venció" in r.json()["detail"]


def test_token_vence_a_los_5_minutos(api, tienda):
    token = _token(api, tienda, 250)
    datos = jwt.get_unverified_claims(token)
    assert datos["exp"] - datos["iat"] == 300


@pytest.mark.parametrize("caso", ["firma-alterada", "token-de-sesion", "basura"])
def test_token_invalido_da_403(api, tienda, caso):
    if caso == "firma-alterada":
        token = _token(api, tienda, 250)
        token = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    elif caso == "token-de-sesion":
        # Un token de sesión de un responsable, aun con los mismos campos, no
        # sirve como autorización: la clave de firma es otra.
        token = create_access_token({**tienda["resp"], "typ": ac.TYP, "jti": "x",
                                     "sub": str(tienda["resp"]["user_id"]),
                                     "punto_id": tienda["id"], "monto": "250.00"})
    else:
        token = "no-es-un-jwt"
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=token))
    assert r.status_code == 403


def test_token_de_autorizacion_no_sirve_como_sesion(api, tienda):
    token = _token(api, tienda, 250)
    r = api.get("/api/ordenes/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_responsable_desactivado_despues_de_autorizar_da_403(api, tienda, S):
    token = _token(api, tienda, 250)
    s = S()
    s.get(Usuario, tienda["resp"]["user_id"]).activo = False
    s.commit()
    s.close()
    r = _crear(api, tienda["vendedor"], _orden(250, autorizacion=token))
    assert r.status_code == 403
    assert "ya no puede" in r.json()["detail"]


def test_tope_de_la_tienda_cambiado_aplica(api, tienda, S):
    s = S()
    s.get(PuntoVenta, tienda["id"]).tope_cargo_entrega = 50
    s.commit()
    s.close()
    assert _crear(api, tienda["vendedor"], _orden(50.01)).status_code == 403
    assert _crear(api, tienda["vendedor"], _orden(50)).status_code == 200


# ---------------------------------------------------------------------------
# POST /api/auth/autorizar-cargo-entrega
# ---------------------------------------------------------------------------


def test_autorizar_emite_token_atado_a_tienda_monto_y_responsable(api, tienda, S):
    r = _autorizar(api, tienda, "250.5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monto"] == "250.50"
    assert body["autorizado_por"] == tienda["resp"]["user_id"]
    datos = jwt.get_unverified_claims(body["autorizacion_cargo"])
    assert datos["punto_id"] == tienda["id"]
    assert datos["monto"] == "250.50"
    assert datos["sub"] == str(tienda["resp"]["user_id"])
    log = _auditoria(S, "AUTORIZACION_CARGO_EMITIDA", usuario_id=tienda["resp"]["user_id"])
    assert log and log[-1].detalle["solicitado_por"] == tienda["vendedor"]["user_id"]
    assert log[-1].detalle["jti"] == datos["jti"]


def test_autorizar_con_contrasena_incorrecta_da_403_y_cuenta_intentos(api, tienda, S):
    r = _autorizar(api, tienda, 250, password="mala")
    assert r.status_code == 403  # nunca 401: no debe cerrar la sesión del vendedor
    s = S()
    assert s.get(Usuario, tienda["resp"]["user_id"]).intentos_fallidos == 1
    s.close()
    logs = _auditoria(S, "AUTORIZACION_CARGO_FALLIDA", punto_id=tienda["id"])
    assert logs[-1].detalle["motivo"] == "password_incorrecto"
    # Con la contraseña correcta se reinician, como en /login.
    assert _autorizar(api, tienda, 250).status_code == 200
    s = S()
    assert s.get(Usuario, tienda["resp"]["user_id"]).intentos_fallidos == 0
    s.close()


def test_autorizar_bloquea_tras_5_intentos_como_el_login(api, tienda, S):
    for _ in range(5):
        assert _autorizar(api, tienda, 250, password="mala").status_code == 403
    s = S()
    u = s.get(Usuario, tienda["resp"]["user_id"])
    assert u.bloqueado_hasta is not None and u.bloqueado_hasta > datetime.utcnow()
    s.close()
    r = _autorizar(api, tienda, 250)  # contraseña correcta, pero bloqueado
    assert r.status_code == 403
    assert "bloqueado" in r.json()["detail"]
    # El bloqueo es el mismo del login.
    r = api.post("/api/auth/login", json={"username": tienda["resp_username"], "password": CLAVE})
    assert r.status_code == 401


def test_autorizar_con_usuario_inexistente_da_403(api, tienda):
    assert _autorizar(api, tienda, 250, username="no_existe_xyz").status_code == 403


def test_vendedor_no_puede_autorizar(api, tienda, S):
    s = S()
    otro = _usuario(s, tienda["empresa_id"], UserRol.TOMADOR_ORDEN, tienda["id"])
    s.commit()
    nombre = otro.username
    s.close()
    r = _autorizar(api, tienda, 250, username=nombre)
    assert r.status_code == 403
    assert "no puede autorizar" in r.json()["detail"]


def test_responsable_de_otra_tienda_no_puede_autorizar(api, tienda, S, empresa_id):
    s = S()
    otra = PuntoVenta(empresa_id=empresa_id, nombre=f"CE otra {uuid.uuid4().hex[:6]}")
    s.add(otra)
    s.flush()
    resp_otra = _usuario(s, empresa_id, UserRol.RESP_TIENDA, otra.id)
    s.commit()
    nombre = resp_otra.username
    s.close()
    assert _autorizar(api, tienda, 250, username=nombre).status_code == 403


def test_gerente_general_sin_tienda_puede_autorizar(api, tienda, S):
    s = S()
    gg = _usuario(s, tienda["empresa_id"], UserRol.GERENTE_GENERAL, None)
    s.commit()
    nombre = gg.username
    s.close()
    token = _token(api, tienda, 250, username=nombre)
    assert _crear(api, tienda["vendedor"], _orden(250, autorizacion=token)).status_code == 200


def test_autorizar_no_acepta_punto_id_en_el_body(api, tienda):
    r = api.post(
        "/api/auth/autorizar-cargo-entrega",
        json={"username": tienda["resp_username"], "password": CLAVE, "monto": 250, "punto_id": 999},
        headers=_auth(tienda["vendedor"]),
    )
    assert r.status_code == 422


@pytest.mark.parametrize("monto", [-5, "1.234"])
def test_autorizar_valida_el_monto(api, tienda, monto):
    assert _autorizar(api, tienda, monto).status_code == 422


# ---------------------------------------------------------------------------
# Tope por tienda (PATCH /api/puntos-venta/{id})
# ---------------------------------------------------------------------------


def _patch_tope(api, usuario, punto_id, valor):
    return api.patch(f"/api/puntos-venta/{punto_id}", json={"tope_cargo_entrega": valor},
                     headers=_auth(usuario))


@pytest.mark.parametrize("rol", [UserRol.ADMIN, UserRol.GERENTE_GENERAL])
def test_gerencia_cambia_el_tope_con_auditoria(api, tienda, S, rol):
    s = S()
    jefe = _cred(_usuario(s, tienda["empresa_id"], rol, None))
    s.commit()
    s.close()
    r = _patch_tope(api, jefe, tienda["id"], "150.50")
    assert r.status_code == 200, r.text
    assert r.json()["tope_cargo_entrega"] == "150.50"
    log = _auditoria(S, "ACTUALIZAR_PUNTO_VENTA", entidad_id=str(tienda["id"]))[-1]
    assert log.usuario_id == jefe["user_id"]
    assert log.detalle["antes"] == {"tope_cargo_entrega": "200.00"}
    assert log.detalle["despues"] == {"tope_cargo_entrega": "150.50"}


@pytest.mark.parametrize("quien", ["vendedor", "resp"])
def test_tienda_no_cambia_su_propio_tope(api, tienda, quien):
    assert _patch_tope(api, tienda[quien], tienda["id"], 500).status_code == 403


@pytest.mark.parametrize("valor", [-1, "10.555"])
def test_tope_invalido_da_422(api, tienda, S, valor):
    s = S()
    jefe = _cred(_usuario(s, tienda["empresa_id"], UserRol.ADMIN, None))
    s.commit()
    s.close()
    assert _patch_tope(api, jefe, tienda["id"], valor).status_code == 422


def test_me_incluye_el_tope_de_la_tienda(api, tienda):
    r = api.get("/api/auth/me", headers=_auth(tienda["vendedor"]))
    assert r.status_code == 200
    assert r.json()["tope_cargo_entrega"] == "200.00"


# ---------------------------------------------------------------------------
# Transacción y cuadre: montos del servidor
# ---------------------------------------------------------------------------


def _transaccion(orden_id, metodo, *, precio_cliente, costo_unitario=10):
    return {
        "orden_id": orden_id,
        "metodo_pago": metodo,
        "precio_venta": precio_cliente,
        "costo_total": 9999,
        "margen_bruto": 9999,
        "margen_pct": 99,
        "items": [{"nombre": "1/4 Pollo", "cantidad": 2, "unidad": "pieza",
                   "precio_unitario": 45.5, "costo_unitario": costo_unitario, "subtotal": 91}],
    }


def test_transaccion_con_orden_usa_total_costo_y_margen_del_servidor(api, tienda, S):
    r = _crear(api, tienda["vendedor"], _orden(25))
    orden_id = r.json()["id"]
    # El cliente manda el precio SIN el cargo (91) y costos inventados.
    r = api.post("/api/ordenes/transacciones/", json=_transaccion(orden_id, "tarjeta", precio_cliente=91),
                 headers=_auth(tienda["vendedor"]))
    assert r.status_code == 200, r.text
    s = S()
    t = s.get(TransaccionVenta, r.json()["id_transaccion"])
    s.close()
    assert t.precio_venta == pytest.approx(116)       # 91 + 25 del servidor
    assert t.costo_total == pytest.approx(20)         # 2 x 10, desde los ítems
    assert t.margen_bruto == pytest.approx(96)
    assert t.margen_pct == pytest.approx(83)
    log = _auditoria(S, "CREAR_TRANSACCION", entidad_id=str(t.id))[0]
    assert log.detalle["total"] == pytest.approx(116)
    assert log.detalle["precio_venta_cliente"] == pytest.approx(91)


def test_cuadre_cuenta_el_total_del_servidor_aunque_el_cliente_mande_otro(api, tienda, S):
    from foodops.api.router_caja import _calcular_efectivo_esperado
    from foodops.db.models_caja import CajaDiaria

    r = _crear(api, tienda["vendedor"], _orden(25, metodo="efectivo"))
    assert r.status_code == 200, r.text
    orden_id = r.json()["id"]
    r = api.post("/api/ordenes/transacciones/", json=_transaccion(orden_id, "efectivo", precio_cliente=1),
                 headers=_auth(tienda["vendedor"]))
    assert r.status_code == 200, r.text
    r = api.post(f"/api/ordenes/{orden_id}/confirmar-cobro",
                 json={"monto_recibido": 116, "vuelto_entregado": 0}, headers=_auth(tienda["resp"]))
    assert r.status_code == 200, r.text

    s = S()
    caja = CajaDiaria(punto_id=tienda["id"], fecha=date.today(), fondo_inicial=0,
                      estado="abierta", abierta_por=tienda["resp"]["user_id"])
    s.add(caja)
    s.commit()
    assert _calcular_efectivo_esperado(s, caja) == 116
    s.close()


# ---------------------------------------------------------------------------
# Reportes e impresión
# ---------------------------------------------------------------------------


def test_reporte_de_cierre_no_cuenta_el_cargo_como_producto(api, tienda, S):
    assert _crear(api, tienda["vendedor"], _orden(25)).status_code == 200
    s = S()
    jefe = _cred(_usuario(s, tienda["empresa_id"], UserRol.ADMIN, None))
    s.commit()
    s.close()
    r = api.get(f"/api/ordenes/reporte/{tienda['id']}", headers=_auth(jefe))
    assert r.status_code == 200, r.text
    productos = [p["producto"] for p in r.json()["top_productos"]]
    assert "1/4 Pollo" in productos
    assert "Cargo de entrega" not in productos
    assert r.json()["total_dinero"] == pytest.approx(116)


def test_payload_del_ticket_lleva_el_tipo_de_cada_item(api, tienda, S):
    from foodops.api.router_impresion import _payload_ticket

    orden_id = _crear(api, tienda["vendedor"], _orden(25)).json()["id"]
    s = S()
    try:
        payload = _payload_ticket(s, s.get(Orden, orden_id), s.get(PuntoVenta, tienda["id"]))
    finally:
        s.close()
    tipos = {i["producto"]: i["tipo"] for i in payload["orden"]["items"]}
    assert tipos == {"1/4 Pollo": "producto", "Cargo de entrega": "entrega"}
