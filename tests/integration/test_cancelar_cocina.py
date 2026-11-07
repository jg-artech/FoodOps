"""Cancelación de órdenes desde cocina: POST /api/ordenes/{id}/cancelar-cocina.

Reglas: solo resp_tienda, gerente_punto, gerente_general y admin; motivo
obligatorio (5 a 200 caracteres tras trim); contraseña PERSONAL del usuario
en sesión con el mismo bloqueo que el login (mismo contador); no se cancela
una orden cobrada ni una ya cancelada; auditoría con motivo y estado previo,
nunca con la contraseña.
"""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.api.router_auth import _MAX_INTENTOS
from foodops.api.router_ordenes import _ROLES_CANCELAR_COCINA, _ROLES_CONFIRMAR_COBRO
from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import (
    AuditLog,
    Empresa,
    MetodoPago,
    Orden,
    OrdenEstado,
    PuntoVenta,
    Usuario,
    UserRol,
)

CLAVE = "Clave-cocina-1"
_HASH = hash_password(CLAVE)
MOTIVO = "Cliente se fue sin esperar"


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def empresa_id(S):
    s = S()
    e = Empresa(nombre="Cancelar Cocina Test", nit=f"TEST-CC-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.commit()
    eid = e.id
    s.close()
    return eid


def _usuario(s, empresa_id, rol, punto_id):
    u = Usuario(
        empresa_id=empresa_id,
        punto_id=punto_id,
        username=f"cc_{uuid.uuid4().hex[:10]}",
        email=f"{uuid.uuid4().hex[:10]}@test.gt",
        password_hash=_HASH,
        rol=rol,
    )
    s.add(u)
    s.flush()
    return {"user_id": u.id, "username": u.username, "punto_id": u.punto_id,
            "rol": u.rol.value, "empresa_id": u.empresa_id}


@pytest.fixture
def tienda(S, empresa_id):
    """Tienda nueva por prueba con un usuario de cada rol (el bloqueo por
    intentos es por usuario: así ninguna prueba arrastra intentos de otra)."""
    s = S()
    p = PuntoVenta(empresa_id=empresa_id, nombre=f"Tienda CC {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()
    out = {"id": p.id, "empresa_id": empresa_id}
    for clave, rol in [
        ("resp", UserRol.RESP_TIENDA),
        ("gerente_punto", UserRol.GERENTE_PUNTO),
        ("cocinero", UserRol.COCINERO),
        ("vendedor", UserRol.TOMADOR_ORDEN),
        ("repartidor", UserRol.REPARTIDOR),
    ]:
        out[clave] = _usuario(s, empresa_id, rol, p.id)
    s.commit()
    s.close()
    return out


def _orden(S, punto_id, *, estado_cobro="pendiente_recibir", estado=OrdenEstado.PENDIENTE,
           metodo=MetodoPago.EFECTIVO):
    s = S()
    o = Orden(punto_id=punto_id, numero_orden=f"TEST-{uuid.uuid4().hex[:12]}", metodo_pago=metodo,
              total=50, estado=estado, estado_cobro=estado_cobro, cliente_nombre="Cliente")
    s.add(o)
    s.commit()
    oid = o.id
    s.close()
    return oid


def _cancelar(api, usuario, orden_id, *, motivo=MOTIVO, password=CLAVE, body=None):
    if body is None:
        body = {"motivo": motivo, "password": password}
    return api.post(f"/api/ordenes/{orden_id}/cancelar-cocina", json=body, headers=_auth(usuario))


def _estado(S, orden_id):
    s = S()
    try:
        o = s.get(Orden, orden_id)
        return o.estado, o.estado_cobro
    finally:
        s.close()


def _usuario_db(S, user_id):
    s = S()
    try:
        u = s.get(Usuario, user_id)
        return u.intentos_fallidos, u.bloqueado_hasta
    finally:
        s.close()


def _auditoria(S, orden_id):
    s = S()
    try:
        return s.execute(
            select(AuditLog).where(AuditLog.entidad == "orden", AuditLog.entidad_id == str(orden_id))
            .order_by(AuditLog.id)
        ).scalars().all()
    finally:
        s.close()


def test_roles_que_cancelan_son_los_que_confirman_cobro():
    assert set(_ROLES_CANCELAR_COCINA) == {"resp_tienda", "gerente_punto", "gerente_general", "admin"}
    assert set(_ROLES_CANCELAR_COCINA) == set(_ROLES_CONFIRMAR_COBRO)


# --- Rol ---------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["cocinero", "vendedor", "repartidor"])
def test_rol_no_permitido_da_403_y_no_cambia_la_orden(api, tienda, S, rol):
    oid = _orden(S, tienda["id"])
    r = _cancelar(api, tienda[rol], oid)
    assert r.status_code == 403
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE


def test_rol_no_permitido_da_403_antes_que_el_motivo(api, tienda, S):
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, tienda["cocinero"], oid, motivo="").status_code == 403


def test_gerente_central_no_puede_cancelar(api, tienda, S):
    s = S()
    gc = _usuario(s, tienda["empresa_id"], UserRol.GERENTE_CENTRAL, None)
    s.commit()
    s.close()
    assert _cancelar(api, gc, _orden(S, tienda["id"])).status_code == 403


# --- Tienda ------------------------------------------------------------------


def test_responsable_de_otra_tienda_da_403(api, tienda, S, empresa_id):
    s = S()
    otra = PuntoVenta(empresa_id=empresa_id, nombre=f"Otra CC {uuid.uuid4().hex[:6]}")
    s.add(otra)
    s.flush()
    otra_id = otra.id
    s.commit()
    s.close()
    oid = _orden(S, otra_id)
    r = _cancelar(api, tienda["resp"], oid)
    assert r.status_code == 403
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE


def test_orden_inexistente_da_404(api, tienda):
    assert _cancelar(api, tienda["resp"], 999_999_999).status_code == 404


# --- Motivo y cuerpo -----------------------------------------------------------


@pytest.mark.parametrize("motivo", [None, "", "    ", "abcd", "  ab c  ", "x" * 201],
                         ids=["ausente", "vacio", "espacios", "4", "4-tras-trim", "201"])
def test_motivo_invalido_da_422(api, tienda, S, motivo):
    oid = _orden(S, tienda["id"])
    body = {"password": CLAVE} if motivo is None else {"motivo": motivo, "password": CLAVE}
    r = _cancelar(api, tienda["resp"], oid, body=body)
    assert r.status_code == 422
    assert "motivo" in r.text.lower()
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE


def test_motivo_con_espacios_se_guarda_recortado(api, tienda, S):
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, tienda["resp"], oid, motivo="   Pedido duplicado   ").status_code == 200
    log = [a for a in _auditoria(S, oid) if a.accion == "ORDEN_CANCELADA_DESDE_COCINA"][0]
    assert log.detalle["motivo"] == "Pedido duplicado"


def test_motivo_de_5_y_de_200_caracteres_es_valido(api, tienda, S):
    assert _cancelar(api, tienda["resp"], _orden(S, tienda["id"]), motivo="abcde").status_code == 200
    assert _cancelar(api, tienda["resp"], _orden(S, tienda["id"]), motivo="y" * 200).status_code == 200


def test_punto_id_en_el_body_da_422(api, tienda, S):
    r = _cancelar(api, tienda["resp"], _orden(S, tienda["id"]),
                  body={"motivo": MOTIVO, "password": CLAVE, "punto_id": 1})
    assert r.status_code == 422


def test_el_422_no_devuelve_la_contrasena(api, tienda, S):
    """Con el 422 por defecto de FastAPI, un campo faltante devuelve el cuerpo
    completo como "input" (contraseña incluida)."""
    secreto = "NoDebeVolver-123"
    oid = _orden(S, tienda["id"])
    for body in ({"password": secreto}, {"motivo": "abc", "password": secreto},
                 {"motivo": MOTIVO, "password": secreto, "extra": secreto}):
        r = _cancelar(api, tienda["resp"], oid, body=body)
        assert r.status_code == 422
        assert secreto not in r.text
        assert all("input" not in e for e in r.json()["detail"])


def test_sin_contrasena_da_422(api, tienda, S):
    r = _cancelar(api, tienda["resp"], _orden(S, tienda["id"]), body={"motivo": MOTIVO})
    assert r.status_code == 422


# --- Estado de la orden --------------------------------------------------------


def test_orden_ya_cancelada_da_409_sin_cambios(api, tienda, S):
    oid = _orden(S, tienda["id"], estado=OrdenEstado.CANCELADO)
    r = _cancelar(api, tienda["resp"], oid)
    assert r.status_code == 409
    assert "ya está cancelada" in r.json()["detail"]
    assert _auditoria(S, oid) == []


@pytest.mark.parametrize("metodo", [MetodoPago.EFECTIVO, MetodoPago.TARJETA, MetodoPago.TRANSFERENCIA])
def test_orden_cobrada_da_409_y_no_cambia(api, tienda, S, metodo):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada", metodo=metodo)
    r = _cancelar(api, tienda["resp"], oid)
    assert r.status_code == 409
    assert "cobrada" in r.json()["detail"]
    assert _estado(S, oid) == (OrdenEstado.PENDIENTE, "cobrada")


def test_orden_cobrada_da_409_antes_de_revisar_la_contrasena(api, tienda, S):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada")
    assert _cancelar(api, tienda["resp"], oid, password="mala").status_code == 409
    assert _usuario_db(S, tienda["resp"]["user_id"])[0] == 0


# --- Contraseña ------------------------------------------------------------------


def test_contrasena_incorrecta_da_401_y_la_orden_no_cambia(api, tienda, S):
    oid = _orden(S, tienda["id"])
    r = _cancelar(api, tienda["resp"], oid, password="mala")
    assert r.status_code == 401
    assert r.json()["detail"] == "Contraseña incorrecta"
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE
    assert _usuario_db(S, tienda["resp"]["user_id"])[0] == 1
    rechazo = [a for a in _auditoria(S, oid) if a.accion == "CANCELACION_COCINA_RECHAZADA"]
    assert len(rechazo) == 1 and rechazo[0].detalle["motivo_rechazo"] == "password_incorrecto"


def test_contrasena_de_otro_usuario_no_sirve(api, tienda, S):
    """Es la contraseña PERSONAL de quien está en sesión, no una compartida."""
    s = S()
    u = s.get(Usuario, tienda["gerente_punto"]["user_id"])
    u.password_hash = hash_password("Otra-clave-99")
    s.commit()
    s.close()
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, tienda["gerente_punto"], oid, password=CLAVE).status_code == 401
    assert _cancelar(api, tienda["gerente_punto"], oid, password="Otra-clave-99").status_code == 200


def test_bloqueo_tras_los_intentos_del_login_y_mismo_mensaje(api, tienda, S):
    resp = tienda["resp"]
    oid = _orden(S, tienda["id"])
    for _ in range(_MAX_INTENTOS):
        assert _cancelar(api, resp, oid, password="mala").status_code == 401
    intentos, bloqueado_hasta = _usuario_db(S, resp["user_id"])
    assert intentos == _MAX_INTENTOS and bloqueado_hasta is not None

    # Bloqueado: con la contraseña correcta, mismo 401 y mismo mensaje.
    r = _cancelar(api, resp, oid)
    assert r.status_code == 401
    assert r.json()["detail"] == "Contraseña incorrecta"
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE

    # Es el mismo bloqueo del login.
    r = api.post("/api/auth/login", json={"username": resp["username"], "password": CLAVE})
    assert r.status_code == 401


def test_intentos_del_login_cuentan_para_cancelar(api, tienda, S):
    """Mismo contador: fallos en el login + fallos al cancelar bloquean juntos."""
    resp = tienda["resp"]
    for _ in range(_MAX_INTENTOS - 1):
        api.post("/api/auth/login", json={"username": resp["username"], "password": "mala"})
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, resp, oid, password="mala").status_code == 401
    assert _usuario_db(S, resp["user_id"])[1] is not None
    assert _cancelar(api, resp, oid).status_code == 401


def test_cancelar_con_contrasena_correcta_reinicia_los_intentos(api, tienda, S):
    resp = tienda["resp"]
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, resp, oid, password="mala").status_code == 401
    assert _cancelar(api, resp, oid).status_code == 200
    assert _usuario_db(S, resp["user_id"]) == (0, None)


# --- Cancelación correcta -------------------------------------------------------


@pytest.mark.parametrize("estado", [OrdenEstado.PENDIENTE, OrdenEstado.PREPARANDO])
def test_cancelacion_correcta_200_y_auditoria(api, tienda, S, estado):
    oid = _orden(S, tienda["id"], estado=estado)
    r = _cancelar(api, tienda["resp"], oid)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cancelado"
    assert _estado(S, oid) == (OrdenEstado.CANCELADO, "pendiente_recibir")

    logs = [a for a in _auditoria(S, oid) if a.accion == "ORDEN_CANCELADA_DESDE_COCINA"]
    assert len(logs) == 1
    log = logs[0]
    assert log.usuario_id == tienda["resp"]["user_id"]
    assert log.punto_id == tienda["id"]
    assert log.created_at is not None
    assert log.detalle["orden_id"] == oid
    assert log.detalle["estado_previo"] == estado.value
    assert log.detalle["estado_cobro_previo"] == "pendiente_recibir"
    assert log.detalle["motivo"] == MOTIVO
    assert log.detalle["cancelada_at"]


def test_gerente_general_sin_tienda_puede_cancelar(api, tienda, S):
    s = S()
    gg = _usuario(s, tienda["empresa_id"], UserRol.GERENTE_GENERAL, None)
    s.commit()
    s.close()
    assert _cancelar(api, gg, _orden(S, tienda["id"])).status_code == 200


def test_auditoria_guarda_el_motivo_y_nunca_la_contrasena(api, tienda, S):
    """El motivo SÍ se guarda en audit_log; la contraseña nunca (ni en la
    cancelación correcta ni en el intento rechazado)."""
    oid = _orden(S, tienda["id"])
    mala = "Intento-Malo-XYZ"
    assert _cancelar(api, tienda["resp"], oid, password=mala).status_code == 401
    assert _cancelar(api, tienda["resp"], oid).status_code == 200
    s = S()
    todos = s.execute(select(AuditLog).where(AuditLog.usuario_id == tienda["resp"]["user_id"])).scalars().all()
    s.close()
    texto = json.dumps([a.detalle for a in todos], ensure_ascii=False)
    assert MOTIVO in texto
    assert CLAVE not in texto and mala not in texto
    assert all("password" not in (a.detalle or {}) for a in todos)


def test_cancelada_no_se_reactiva_por_este_endpoint(api, tienda, S):
    oid = _orden(S, tienda["id"])
    assert _cancelar(api, tienda["resp"], oid).status_code == 200
    assert _cancelar(api, tienda["resp"], oid).status_code == 409
    assert _estado(S, oid)[0] == OrdenEstado.CANCELADO


# =============================================================================
# POST /api/ordenes/{id}/cancelar (Órdenes del POS): mismos roles, motivo y
# contraseña; a diferencia de cocina, SÍ cancela órdenes cobradas y deja la
# devolución registrada como pendiente.
# =============================================================================


def _cancelar_pos(api, usuario, orden_id, *, motivo=MOTIVO, password=CLAVE, body=None):
    if body is None:
        body = {"motivo": motivo, "password": password}
    return api.post(f"/api/ordenes/{orden_id}/cancelar", json=body, headers=_auth(usuario))


@pytest.mark.parametrize("rol", ["cocinero", "vendedor", "repartidor"])
def test_pos_rol_no_permitido_da_403(api, tienda, S, rol):
    oid = _orden(S, tienda["id"])
    assert _cancelar_pos(api, tienda[rol], oid).status_code == 403
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE


@pytest.mark.parametrize("motivo", [None, "abcd", "   "], ids=["ausente", "corto", "espacios"])
def test_pos_motivo_obligatorio_tambien_en_cobradas(api, tienda, S, motivo):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada", metodo=MetodoPago.TARJETA)
    body = {"password": CLAVE} if motivo is None else {"motivo": motivo, "password": CLAVE}
    r = _cancelar_pos(api, tienda["resp"], oid, body=body)
    assert r.status_code == 422
    assert CLAVE not in r.text
    assert _estado(S, oid)[0] == OrdenEstado.PENDIENTE


def test_pos_contrasena_incorrecta_da_401_y_no_cancela(api, tienda, S):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada")
    r = _cancelar_pos(api, tienda["resp"], oid, password="mala")
    assert r.status_code == 401
    assert r.json()["detail"] == "Contraseña incorrecta"
    assert _estado(S, oid) == (OrdenEstado.PENDIENTE, "cobrada")
    rechazo = [a for a in _auditoria(S, oid) if a.accion == "CANCELACION_ORDEN_RECHAZADA"]
    assert len(rechazo) == 1 and rechazo[0].detalle["origen"] == "pos"


def test_pos_cuenta_en_el_mismo_bloqueo(api, tienda, S):
    resp = tienda["resp"]
    oid = _orden(S, tienda["id"])
    for _ in range(_MAX_INTENTOS):
        assert _cancelar_pos(api, resp, oid, password="mala").status_code == 401
    assert _usuario_db(S, resp["user_id"])[1] is not None
    assert _cancelar_pos(api, resp, oid).status_code == 401
    assert _cancelar(api, resp, oid).status_code == 401  # también bloqueado en cocina


def test_pos_ya_cancelada_da_409(api, tienda, S):
    oid = _orden(S, tienda["id"], estado=OrdenEstado.CANCELADO)
    assert _cancelar_pos(api, tienda["resp"], oid).status_code == 409


def test_pos_tienda_ajena_da_403(api, tienda, S, empresa_id):
    s = S()
    otra = PuntoVenta(empresa_id=empresa_id, nombre=f"Otra POS {uuid.uuid4().hex[:6]}")
    s.add(otra)
    s.commit()
    otra_id = otra.id
    s.close()
    assert _cancelar_pos(api, tienda["resp"], _orden(S, otra_id)).status_code == 403


def test_pos_cancela_orden_pendiente_sin_devolucion(api, tienda, S):
    oid = _orden(S, tienda["id"])
    r = _cancelar_pos(api, tienda["gerente_punto"], oid)
    assert r.status_code == 200, r.text
    assert r.json()["devolucion_pendiente"] is False
    log = [a for a in _auditoria(S, oid) if a.accion == "ORDEN_CANCELADA"][0]
    assert log.detalle["origen"] == "pos"
    assert log.detalle["motivo"] == MOTIVO
    assert "devolucion_pendiente" not in log.detalle


@pytest.mark.parametrize("metodo", [MetodoPago.EFECTIVO, MetodoPago.TARJETA, MetodoPago.TRANSFERENCIA])
def test_pos_cancela_orden_cobrada_con_motivo_y_devolucion_pendiente(api, tienda, S, metodo):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada", metodo=metodo, estado=OrdenEstado.PREPARANDO)
    r = _cancelar_pos(api, tienda["resp"], oid, motivo="  Cliente pidió devolución  ")
    assert r.status_code == 200, r.text
    assert r.json() == {"id": oid, "numero_orden": r.json()["numero_orden"], "estado": "cancelado",
                        "devolucion_pendiente": True}
    assert _estado(S, oid) == (OrdenEstado.CANCELADO, "cobrada")
    logs = [a for a in _auditoria(S, oid) if a.accion == "ORDEN_CANCELADA"]
    assert len(logs) == 1
    d = logs[0].detalle
    assert d["motivo"] == "Cliente pidió devolución"
    assert d["estado_previo"] == "preparando"
    assert d["estado_cobro_previo"] == "cobrada"
    assert d["monto_cobrado"] == 50.0
    assert d["metodo_pago"] == metodo.value
    assert d["devolucion_pendiente"] is True
    assert CLAVE not in json.dumps(d, ensure_ascii=False)


def test_cocina_sigue_sin_cancelar_cobradas_y_remite_al_pos(api, tienda, S):
    oid = _orden(S, tienda["id"], estado_cobro="cobrada", metodo=MetodoPago.TARJETA)
    r = _cancelar(api, tienda["resp"], oid)
    assert r.status_code == 409
    assert "Órdenes" in r.json()["detail"]


def test_pos_cobrada_en_efectivo_cancelada_sale_del_cuadre(api, tienda, S):
    """Una venta en efectivo COBRADA y luego cancelada deja de contar en el
    efectivo esperado (el dinero se devuelve al cliente)."""
    from datetime import date

    from foodops.api.router_caja import _calcular_efectivo_esperado
    from foodops.db.models import TransaccionVenta
    from foodops.db.models_caja import CajaDiaria

    oid = _orden(S, tienda["id"], estado_cobro="cobrada")
    s = S()
    s.add(TransaccionVenta(punto_id=tienda["id"], orden_id=oid, metodo_pago="efectivo", precio_venta=50))
    caja = CajaDiaria(punto_id=tienda["id"], fecha=date.today(), fondo_inicial=0, estado="abierta",
                      abierta_por=tienda["resp"]["user_id"])
    s.add(caja)
    s.commit()
    assert _calcular_efectivo_esperado(s, caja) == 50
    assert _cancelar_pos(api, tienda["resp"], oid).status_code == 200
    s.expire_all()
    assert _calcular_efectivo_esperado(s, caja) == 0
    s.close()
