"""Matriz de permisos del rol tomador_orden (vendedor) y cambios de estado.

Reglas (CLAUDE.md y core/permisos_ordenes.py):
- El vendedor crea órdenes y ve las de HOY (hora de Guatemala) de su tienda.
  No cambia estados de cocina, no cancela, no ve caja, cierres ni totales
  del día, ni ninguna pantalla de administración.
- PUT /status: "cancelado" es 409 para todos; listo/preparando solo cocina y
  superiores; entregado además el repartidor; una orden cancelada no se
  reactiva.
- La protección es del backend: el barrido de rutas comprueba que cualquier
  endpoint fuera de la lista de permitidos le responde 403 al vendedor.
"""

import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.core.permisos_ordenes import (
    ROLES_CAMBIAR_ESTADO_COCINA,
    ROLES_CANCELAR,
    ROLES_MARCAR_ENTREGADO,
    ROLES_MARCAR_LISTO,
)
from foodops.db.models import (
    Empresa,
    MetodoPago,
    Orden,
    OrdenEstado,
    OrdenItem,
    PuntoVenta,
    TrabajoImpresion,
    Usuario,
    UserRol,
)
from foodops.main import app
from foodops.utils.timeutils import limites_hoy_guatemala

CLAVE = "Clave-vendedor-1"
_HASH = hash_password(CLAVE)


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def datos(S):
    """Dos tiendas de la misma empresa; un usuario de cada rol en la tienda A
    (gerencia sin tienda); órdenes de hoy, de ayer y de la tienda B."""
    s = S()
    e = Empresa(nombre="Permisos Vendedor Test", nit=f"TEST-PV-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    a = PuntoVenta(empresa_id=e.id, nombre=f"Tienda A {uuid.uuid4().hex[:6]}")
    b = PuntoVenta(empresa_id=e.id, nombre=f"Tienda B {uuid.uuid4().hex[:6]}")
    s.add_all([a, b])
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"pv_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=rol,
        )
        s.add(u)
        s.flush()
        return {"user_id": u.id, "username": u.username, "punto_id": u.punto_id,
                "rol": u.rol.value, "empresa_id": u.empresa_id}

    out = {"a": a.id, "b": b.id, "empresa_id": e.id}
    for clave, rol, punto in [
        ("tomador_orden", UserRol.TOMADOR_ORDEN, a.id),
        ("tomador_orden_2", UserRol.TOMADOR_ORDEN, a.id),
        ("cocinero", UserRol.COCINERO, a.id),
        ("repartidor", UserRol.REPARTIDOR, a.id),
        ("resp_tienda", UserRol.RESP_TIENDA, a.id),
        ("gerente_punto", UserRol.GERENTE_PUNTO, a.id),
        ("gerente_general", UserRol.GERENTE_GENERAL, None),
        ("admin", UserRol.ADMIN, None),
        ("gerente_central", UserRol.GERENTE_CENTRAL, None),
    ]:
        out[clave] = usuario(rol, punto)

    inicio_hoy, _ = limites_hoy_guatemala()
    ordenes = {
        # Hoy en Guatemala, en los dos bordes del día.
        "a_hoy_temprano": (a.id, inicio_hoy + timedelta(minutes=30)),
        "a_hoy": (a.id, datetime.utcnow()),
        # 23:30 de ayer en Guatemala (ya es "hoy" en UTC si son más de las 05:30 UTC).
        "a_ayer_noche": (a.id, inicio_hoy - timedelta(minutes=30)),
        "a_hace_3_dias": (a.id, datetime.utcnow() - timedelta(days=3)),
        "b_hoy": (b.id, datetime.utcnow()),
    }
    for clave, (punto_id, creada) in ordenes.items():
        o = Orden(punto_id=punto_id, numero_orden=f"PV-{clave}-{uuid.uuid4().hex[:8]}",
                  metodo_pago=MetodoPago.EFECTIVO, total=50, estado=OrdenEstado.PENDIENTE,
                  estado_cobro="pendiente_recibir", cliente_nombre="Cliente", created_at=creada)
        s.add(o)
        s.flush()
        out[f"orden_{clave}"] = o.id
        out[f"numero_{clave}"] = o.numero_orden

    for clave, creado in [("hoy", datetime.utcnow()), ("ayer", inicio_hoy - timedelta(hours=2))]:
        t = TrabajoImpresion(punto_id=a.id, tipo="ticket", payload={}, estado="ok",
                             solicitado_por=out["resp_tienda"]["user_id"], created_at=creado)
        s.add(t)
        s.flush()
        out[f"trabajo_{clave}"] = t.id
    s.commit()
    s.close()
    return out


def _orden_nueva(S, punto_id, estado=OrdenEstado.PENDIENTE):
    s = S()
    o = Orden(punto_id=punto_id, numero_orden=f"PV-{uuid.uuid4().hex[:12]}", metodo_pago=MetodoPago.EFECTIVO,
              total=50, estado=estado, estado_cobro="pendiente_recibir", cliente_nombre="Cliente")
    s.add(o)
    s.commit()
    oid = o.id
    s.close()
    return oid


def _estado(S, orden_id):
    s = S()
    try:
        return s.get(Orden, orden_id).estado
    finally:
        s.close()


def _status(api, usuario, orden_id, estado):
    return api.put(f"/api/ordenes/{orden_id}/status", json={"estado": estado}, headers=_auth(usuario))


# ---------------------------------------------------------------------------
# Constantes de permisos
# ---------------------------------------------------------------------------


def test_vendedor_no_esta_en_ninguna_lista_de_cambio_de_estado_ni_cancelacion():
    for roles in (ROLES_MARCAR_LISTO, ROLES_MARCAR_ENTREGADO, ROLES_CAMBIAR_ESTADO_COCINA, ROLES_CANCELAR):
        assert "tomador_orden" not in roles


def test_repartidor_entrega_pero_no_marca_listo_ni_cancela():
    assert "repartidor" in ROLES_MARCAR_ENTREGADO
    assert "repartidor" not in ROLES_MARCAR_LISTO
    assert "repartidor" not in ROLES_CANCELAR


# ---------------------------------------------------------------------------
# PUT /status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["pendiente", "preparando", "listo", "entregado"])
def test_vendedor_no_cambia_el_estado_de_cocina(api, datos, S, estado):
    orden_id = _orden_nueva(S, datos["a"], OrdenEstado.PREPARANDO if estado == "pendiente" else OrdenEstado.PENDIENTE)
    antes = _estado(S, orden_id)
    r = _status(api, datos["tomador_orden"], orden_id, estado)
    assert r.status_code == 403
    assert r.json()["detail"] == "No autorizado para cambiar el estado de cocina"
    assert _estado(S, orden_id) == antes


@pytest.mark.parametrize("rol", ["tomador_orden", "cocinero", "repartidor", "resp_tienda",
                                 "gerente_punto", "gerente_general", "admin", "gerente_central"])
def test_cancelar_por_put_status_es_409_para_todos_y_no_cambia_la_orden(api, datos, S, rol):
    orden_id = _orden_nueva(S, datos["a"])
    r = _status(api, datos[rol], orden_id, "cancelado")
    assert r.status_code == 409
    assert "/cancelar-cocina" in r.json()["detail"] and "/cancelar)" in r.json()["detail"]
    assert _estado(S, orden_id) == OrdenEstado.PENDIENTE


@pytest.mark.parametrize("estado", ["preparando", "listo"])
def test_repartidor_no_marca_listo_ni_preparando(api, datos, S, estado):
    orden_id = _orden_nueva(S, datos["a"])
    r = _status(api, datos["repartidor"], orden_id, estado)
    assert r.status_code == 403
    assert _estado(S, orden_id) == OrdenEstado.PENDIENTE


def test_repartidor_marca_entregado(api, datos, S):
    orden_id = _orden_nueva(S, datos["a"], OrdenEstado.LISTO)
    r = _status(api, datos["repartidor"], orden_id, "entregado")
    assert r.status_code == 200
    assert _estado(S, orden_id) == OrdenEstado.ENTREGADO


@pytest.mark.parametrize("rol", ["cocinero", "resp_tienda", "gerente_punto", "gerente_general", "admin"])
@pytest.mark.parametrize("estado", ["preparando", "listo", "entregado"])
def test_cocina_y_superiores_cambian_el_estado(api, datos, S, rol, estado):
    orden_id = _orden_nueva(S, datos["a"])
    r = _status(api, datos[rol], orden_id, estado)
    assert r.status_code == 200
    assert _estado(S, orden_id) == OrdenEstado(estado)


@pytest.mark.parametrize("estado", ["pendiente", "preparando", "listo", "entregado"])
def test_orden_cancelada_no_se_reactiva(api, datos, S, estado):
    orden_id = _orden_nueva(S, datos["a"], OrdenEstado.CANCELADO)
    r = _status(api, datos["resp_tienda"], orden_id, estado)
    assert r.status_code == 409
    assert _estado(S, orden_id) == OrdenEstado.CANCELADO


def test_estado_invalido_da_400(api, datos, S):
    orden_id = _orden_nueva(S, datos["a"])
    r = _status(api, datos["resp_tienda"], orden_id, "volando")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Cancelar y confirmar cobro: el vendedor no puede
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["cancelar", "cancelar-cocina"])
def test_vendedor_no_cancela_por_ninguna_ruta(api, datos, S, ruta):
    orden_id = _orden_nueva(S, datos["a"])
    r = api.post(f"/api/ordenes/{orden_id}/{ruta}",
                 json={"motivo": "Cliente se fue", "password": CLAVE}, headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 403
    assert _estado(S, orden_id) == OrdenEstado.PENDIENTE


def test_vendedor_no_confirma_cobro(api, datos, S):
    orden_id = _orden_nueva(S, datos["a"])
    r = api.post(f"/api/ordenes/{orden_id}/confirmar-cobro", json={"dinero_recibido": 50},
                 headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Listado de órdenes: el vendedor solo ve las de hoy de su tienda
# ---------------------------------------------------------------------------


def _numeros(r):
    return {o["numero_orden"] for o in r.json()}


def test_vendedor_ve_solo_las_ordenes_de_hoy_de_su_tienda(api, datos):
    r = api.get("/api/ordenes/", headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 200
    numeros = _numeros(r)
    assert datos["numero_a_hoy"] in numeros
    assert datos["numero_a_hoy_temprano"] in numeros
    assert datos["numero_a_ayer_noche"] not in numeros
    assert datos["numero_a_hace_3_dias"] not in numeros
    assert datos["numero_b_hoy"] not in numeros


@pytest.mark.parametrize("tienda", ["a", "b"])
def test_vendedor_que_pide_una_tienda_recibe_403(api, datos, tienda):
    r = api.get("/api/ordenes/", params={"punto_id": datos[tienda]}, headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 403


def test_vendedor_no_puede_ampliar_la_fecha_con_parametros(api, datos):
    r = api.get("/api/ordenes/", params={"fecha": "2020-01-01", "desde": "2020-01-01", "todas": "1"},
                headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 200
    assert datos["numero_a_hace_3_dias"] not in _numeros(r)
    assert datos["numero_a_ayer_noche"] not in _numeros(r)


@pytest.mark.parametrize("rol", ["cocinero", "repartidor", "resp_tienda", "gerente_punto"])
def test_los_demas_roles_de_tienda_siguen_viendo_dias_anteriores(api, datos, rol):
    r = api.get("/api/ordenes/", headers=_auth(datos[rol]))
    assert r.status_code == 200
    numeros = _numeros(r)
    assert datos["numero_a_hace_3_dias"] in numeros
    assert datos["numero_b_hoy"] not in numeros


def test_limites_de_hoy_usan_hora_de_guatemala():
    # 05:59 UTC del 16 = 23:59 del 15 en Guatemala; 06:00 UTC = 00:00 del 16.
    inicio, fin = limites_hoy_guatemala(datetime(2026, 11, 16, 5, 59))
    assert (inicio, fin) == (datetime(2026, 11, 15, 6, 0), datetime(2026, 11, 16, 6, 0))
    inicio, fin = limites_hoy_guatemala(datetime(2026, 11, 16, 6, 0))
    assert (inicio, fin) == (datetime(2026, 11, 16, 6, 0), datetime(2026, 11, 17, 6, 0))


# ---------------------------------------------------------------------------
# Trabajos de impresión: el vendedor solo ve los de hoy
# ---------------------------------------------------------------------------


def test_vendedor_ve_solo_trabajos_de_impresion_de_hoy(api, datos):
    r = api.get("/api/impresion/trabajos", headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert datos["trabajo_hoy"] in ids
    assert datos["trabajo_ayer"] not in ids


def test_responsable_sigue_viendo_trabajos_anteriores(api, datos):
    r = api.get("/api/impresion/trabajos", headers=_auth(datos["resp_tienda"]))
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert {datos["trabajo_hoy"], datos["trabajo_ayer"]} <= ids


# ---------------------------------------------------------------------------
# Total del día y cierre: el vendedor no los obtiene de la API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", [
    "/api/ordenes/reporte/{a}",
    "/api/ordenes/reporte-rentabilidad/{a}",
    "/api/caja/reporte-cierre",
    "/api/caja/actual",
    "/api/gerencia/dashboard",
    "/api/gerencia/dashboard/multi-tienda",
])
def test_vendedor_no_obtiene_el_total_del_dia_ni_el_cierre(api, datos, ruta):
    r = api.get(ruta.format(a=datos["a"]), headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 403, f"{ruta} -> {r.status_code}"


def test_vendedor_no_cierra_caja(api, datos):
    r = api.post("/api/caja/cerrar", json={"efectivo_contado": 0}, headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Lo permitido sigue funcionando
# ---------------------------------------------------------------------------


def test_vendedor_crea_una_orden_y_la_ve_en_su_listado(api, datos):
    r = api.post("/api/ordenes/", json={
        "cliente_nombre": "Cliente vendedor",
        "metodo_pago": "efectivo",
        "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 25}],
    }, headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 200, r.text
    numero = r.json()["numero_orden"]
    r = api.get("/api/ordenes/", headers=_auth(datos["tomador_orden"]))
    assert numero in _numeros(r)


def _orden_de(S, punto_id, usuario, total):
    """Orden de hoy tomada por `usuario`. Directo en la BD: por el endpoint,
    dos órdenes de la misma tienda en el mismo segundo chocan en
    numero_orden (fallo conocido, fuera de esta prueba)."""
    s = S()
    o = Orden(punto_id=punto_id, numero_orden=f"PV-{uuid.uuid4().hex[:12]}", metodo_pago=MetodoPago.EFECTIVO,
              total=total, estado=OrdenEstado.PENDIENTE, estado_cobro="pendiente_recibir",
              cliente_nombre="Cliente importes", tomada_por=usuario["user_id"])
    s.add(o)
    s.commit()
    oid = o.id
    s.close()
    return oid


def test_vendedor_ve_su_total_y_no_el_de_otro_vendedor_de_su_tienda(api, datos, S):
    propia = _orden_de(S, datos["a"], datos["tomador_orden"], 25)
    ajena = _orden_de(S, datos["a"], datos["tomador_orden_2"], 41)

    vista = {o["id"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["tomador_orden"])).json()}
    assert vista[propia]["total"] == 25.0
    assert "total_oculto" not in vista[propia]
    assert vista[ajena]["total"] is None
    assert vista[ajena]["total_oculto"] is True

    # El otro vendedor, al revés.
    vista_2 = {o["id"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["tomador_orden_2"])).json()}
    assert vista_2[ajena]["total"] == 41.0
    assert vista_2[propia]["total"] is None

    # Fuera de los importes, la orden ajena llega igual que la ve el responsable.
    resp = {o["id"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["resp_tienda"])).json()}
    importes = ("total", "total_oculto", "items")
    sin_total = {k: v for k, v in vista[ajena].items() if k not in importes}
    assert sin_total == {k: v for k, v in resp[ajena].items() if k not in importes}


def _item_de(S, orden_id, producto, precio, tipo="producto"):
    s = S()
    s.add(OrdenItem(orden_id=orden_id, producto=producto, cantidad=1, precio_unitario=precio,
                    subtotal=precio, tipo=tipo))
    s.commit()
    s.close()


def test_items_de_orden_ajena_salen_sin_importes_al_vendedor(api, datos, S):
    propia = _orden_de(S, datos["a"], datos["tomador_orden"], 45.5)
    ajena = _orden_de(S, datos["a"], datos["tomador_orden_2"], 60.5)
    _item_de(S, propia, "1/4 Pollo", 45.5)
    _item_de(S, ajena, "1/4 Pollo", 45.5)
    _item_de(S, ajena, "Cargo de entrega", 15, tipo="entrega")

    vista = {o["id"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["tomador_orden"])).json()}
    assert [(i["precio_unitario"], i["subtotal"]) for i in vista[propia]["items"]] == [(45.5, 45.5)]
    assert len(vista[ajena]["items"]) == 2
    assert all(i["precio_unitario"] is None and i["subtotal"] is None for i in vista[ajena]["items"])

    # Producto, cantidad, especiales y tipo llegan igual que al responsable.
    resp = {o["id"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["resp_tienda"])).json()}
    sin_importes = lambda items: [  # noqa: E731
        {k: v for k, v in i.items() if k not in ("precio_unitario", "subtotal")} for i in items
    ]
    assert sin_importes(vista[ajena]["items"]) == sin_importes(resp[ajena]["items"])
    assert {i["subtotal"] for i in resp[ajena]["items"]} == {45.5, 15.0}


def test_ordenes_sin_vendedor_tambien_ocultan_el_total_al_vendedor(api, datos):
    vista = {o["numero_orden"]: o for o in api.get("/api/ordenes/", headers=_auth(datos["tomador_orden"])).json()}
    assert vista[datos["numero_a_hoy"]]["total"] is None


@pytest.mark.parametrize("rol", ["cocinero", "repartidor", "resp_tienda", "gerente_punto"])
def test_los_demas_roles_ven_todos_los_totales(api, datos, rol):
    ordenes = api.get("/api/ordenes/", headers=_auth(datos[rol])).json()
    assert ordenes and all(o["total"] is not None and "total_oculto" not in o for o in ordenes)


@pytest.mark.parametrize("ruta", ["/api/auth/me", "/api/productos-menu"])
def test_vendedor_lee_lo_que_necesita_el_pos(api, datos, ruta):
    r = api.get(ruta, headers=_auth(datos["tomador_orden"]))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Barrido: cualquier endpoint fuera de la lista de permitidos le da 403
# ---------------------------------------------------------------------------

# (método, ruta) que el vendedor SÍ puede usar. Todo lo demás debe ser 403.
PERMITIDAS_VENDEDOR = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/autorizar-cargo-entrega"),
    ("GET", "/api/ordenes/"),
    ("POST", "/api/ordenes/"),
    ("POST", "/api/ordenes/transacciones/"),
    ("PUT", "/api/ordenes/{orden_id}/datos-factura"),
    ("GET", "/api/productos-menu"),
    ("POST", "/api/impresion/ticket"),
    ("GET", "/api/impresion/trabajos"),
    ("POST", "/api/impresion/trabajos/{trabajo_id}/reintentar"),
    ("GET", "/"),
    ("GET", "/health"),
}
# Endpoints del agente de impresión: no usan el JWT de usuario (token propio
# del agente), así que el vendedor recibe 401/403 de otra dependencia.
_AGENTE = re.compile(r"^/api/impresion/agente/(pendientes|trabajos/)")
# Responde 403 dentro del handler (con auditoría), después de validar el body.
_BODY_PARA_403 = {("POST", "/api/impresion/abrir-cajon"): {"punto_id": None, "motivo": "prueba barrido"}}


def _rutas_api():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield metodo, r.path


def test_barrido_todas_las_rutas_fuera_de_la_lista_dan_403_al_vendedor(api, datos):
    malas = []
    revisadas = 0
    for metodo, ruta in _rutas_api():
        if (metodo, ruta) in PERMITIDAS_VENDEDOR or _AGENTE.match(ruta):
            continue
        url = re.sub(r"\{[^}]+\}", "1", ruta)
        body = _BODY_PARA_403.get((metodo, ruta), {"estado": "listo"} if ruta.endswith("/status") else {})
        r = api.request(metodo, url, json=body, headers=_auth(datos["tomador_orden"]))
        revisadas += 1
        if r.status_code != 403:
            malas.append(f"{metodo} {ruta} -> {r.status_code}")
    assert revisadas > 50
    assert not malas, "\n".join(malas)


def test_la_lista_de_permitidas_no_tiene_rutas_que_ya_no_existen():
    existentes = set(_rutas_api())
    assert PERMITIDAS_VENDEDOR <= existentes
