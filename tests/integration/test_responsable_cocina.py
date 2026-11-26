"""Personal de cocina y responsable por orden (migración 016).

Reglas (decisiones del 2026-11-25):
- Sin vínculo entre usuario y personal: el cocinero elige a cualquier persona
  activa de su tienda, pero solo si la orden aún no tiene responsable.
  Reasignar es de resp_tienda, gerente_punto, gerente_general y admin.
- Con la orden en listo, entregado o cancelado no se cambia el responsable.
- La primera asignación pasa pendiente -> preparando y guarda en_preparacion_at.
- Sin responsable no se pasa a listo ni a entregado, salvo las órdenes
  anteriores a la migración (exige_responsable_cocina = false).
- El personal lo administran resp_tienda (su tienda), gerente_general y admin.
  Sin DELETE: se desactiva con PATCH.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import (
    AuditLog,
    Empresa,
    MetodoPago,
    Orden,
    OrdenEstado,
    PersonalCocina,
    PuntoVenta,
    Usuario,
    UserRol,
)

_HASH = hash_password("Clave-cocina-1")


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def datos(S):
    s = S()
    e = Empresa(nombre="Cocina Test", nit=f"TEST-CO-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    a = PuntoVenta(empresa_id=e.id, nombre=f"Tienda A {uuid.uuid4().hex[:6]}")
    b = PuntoVenta(empresa_id=e.id, nombre=f"Tienda B {uuid.uuid4().hex[:6]}")
    s.add_all([a, b])
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"co_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=rol,
        )
        s.add(u)
        s.flush()
        return {"user_id": u.id, "username": u.username, "punto_id": u.punto_id,
                "rol": u.rol.value, "empresa_id": u.empresa_id}

    out = {"a": a.id, "b": b.id}
    for clave, rol, punto in [
        ("cocinero", UserRol.COCINERO, a.id),
        ("resp_tienda", UserRol.RESP_TIENDA, a.id),
        ("gerente_punto", UserRol.GERENTE_PUNTO, a.id),
        ("gerente_general", UserRol.GERENTE_GENERAL, None),
        ("admin", UserRol.ADMIN, None),
        ("repartidor", UserRol.REPARTIDOR, a.id),
        ("tomador_orden", UserRol.TOMADOR_ORDEN, a.id),
        ("resp_b", UserRol.RESP_TIENDA, b.id),
    ]:
        out[clave] = usuario(rol, punto)
    s.commit()
    s.close()
    return out


def _persona(S, punto_id, activo=True):
    s = S()
    p = PersonalCocina(punto_id=punto_id, nombre=f"Cocinero {uuid.uuid4().hex[:8]}", activo=activo)
    s.add(p)
    s.commit()
    pid = p.id
    s.close()
    return pid


def _orden(S, punto_id, estado=OrdenEstado.PENDIENTE, responsable_id=None, exige=True):
    s = S()
    o = Orden(punto_id=punto_id, numero_orden=f"CO-{uuid.uuid4().hex[:12]}", metodo_pago=MetodoPago.TARJETA,
              total=50, estado=estado, estado_cobro="cobrada", cliente_nombre="Cliente cocina",
              responsable_cocina_id=responsable_id, exige_responsable_cocina=exige)
    s.add(o)
    s.commit()
    oid = o.id
    s.close()
    return oid


def _orden_bd(S, orden_id):
    s = S()
    try:
        return s.get(Orden, orden_id)
    finally:
        s.close()


def _asignar(api, usuario, orden_id, personal_id):
    return api.put(f"/api/ordenes/{orden_id}/responsable-cocina",
                   json={"personal_id": personal_id}, headers=_auth(usuario))


def _status(api, usuario, orden_id, estado):
    return api.put(f"/api/ordenes/{orden_id}/status", json={"estado": estado}, headers=_auth(usuario))


# ---------------------------------------------------------------------------
# Asignar responsable
# ---------------------------------------------------------------------------


def test_cocinero_se_asigna_y_la_orden_pasa_a_preparando(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    r = _asignar(api, datos["cocinero"], orden_id, persona)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "preparando"
    assert r.json()["responsable_cocina"]["id"] == persona
    assert r.json()["en_preparacion_at"] is not None
    o = _orden_bd(S, orden_id)
    assert o.estado == OrdenEstado.PREPARANDO
    assert o.responsable_cocina_id == persona
    assert o.en_preparacion_at is not None


def test_primera_asignacion_en_orden_ya_en_preparando_registra_la_hora(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"], OrdenEstado.PREPARANDO)
    r = _asignar(api, datos["cocinero"], orden_id, persona)
    assert r.status_code == 200
    o = _orden_bd(S, orden_id)
    assert o.estado == OrdenEstado.PREPARANDO
    assert o.en_preparacion_at is not None


def test_cocinero_no_reasigna_a_otro(api, datos, S):
    primero, otro = _persona(S, datos["a"]), _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"], OrdenEstado.PREPARANDO, responsable_id=primero)
    r = _asignar(api, datos["cocinero"], orden_id, otro)
    assert r.status_code == 403
    assert _orden_bd(S, orden_id).responsable_cocina_id == primero


@pytest.mark.parametrize("rol", ["resp_tienda", "gerente_punto", "gerente_general", "admin"])
def test_gerencia_reasigna(api, datos, S, rol):
    primero, otro = _persona(S, datos["a"]), _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"], OrdenEstado.PREPARANDO, responsable_id=primero)
    r = _asignar(api, datos[rol], orden_id, otro)
    assert r.status_code == 200, r.text
    assert _orden_bd(S, orden_id).responsable_cocina_id == otro


def test_personal_de_otra_tienda_da_403(api, datos, S):
    de_b = _persona(S, datos["b"])
    orden_id = _orden(S, datos["a"])
    r = _asignar(api, datos["resp_tienda"], orden_id, de_b)
    assert r.status_code == 403
    assert _orden_bd(S, orden_id).responsable_cocina_id is None


def test_orden_de_otra_tienda_da_403(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    r = _asignar(api, datos["resp_b"], orden_id, persona)
    assert r.status_code == 403
    assert _orden_bd(S, orden_id).responsable_cocina_id is None


def test_personal_inactivo_da_422(api, datos, S):
    inactivo = _persona(S, datos["a"], activo=False)
    orden_id = _orden(S, datos["a"])
    r = _asignar(api, datos["resp_tienda"], orden_id, inactivo)
    assert r.status_code == 422
    assert _orden_bd(S, orden_id).responsable_cocina_id is None


@pytest.mark.parametrize("estado", [OrdenEstado.LISTO, OrdenEstado.ENTREGADO, OrdenEstado.CANCELADO])
def test_orden_en_listo_entregado_o_cancelado_da_409(api, datos, S, estado):
    primero, otro = _persona(S, datos["a"]), _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"], estado, responsable_id=primero)
    r = _asignar(api, datos["resp_tienda"], orden_id, otro)
    assert r.status_code == 409
    assert _orden_bd(S, orden_id).responsable_cocina_id == primero


@pytest.mark.parametrize("rol", ["repartidor", "tomador_orden"])
def test_repartidor_y_vendedor_no_asignan(api, datos, S, rol):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos[rol], orden_id, persona).status_code == 403


def test_auditoria_con_antes_y_despues(api, datos, S):
    primero, otro = _persona(S, datos["a"]), _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos["cocinero"], orden_id, primero).status_code == 200
    assert _asignar(api, datos["resp_tienda"], orden_id, otro).status_code == 200
    s = S()
    filas = s.execute(
        select(AuditLog).where(
            AuditLog.accion == "ORDEN_RESPONSABLE_COCINA_ASIGNADO",
            AuditLog.entidad_id == str(orden_id),
        ).order_by(AuditLog.id)
    ).scalars().all()
    s.close()
    assert len(filas) == 2
    assert filas[0].detalle["antes"] is None
    assert filas[0].detalle["despues"]["id"] == primero
    assert filas[0].detalle["estado_previo"] == "pendiente"
    assert filas[0].detalle["estado_nuevo"] == "preparando"
    assert filas[1].detalle["antes"]["id"] == primero
    assert filas[1].detalle["despues"]["id"] == otro
    assert filas[1].usuario_id == datos["resp_tienda"]["user_id"]


def test_asignar_la_misma_persona_no_audita_de_nuevo(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos["cocinero"], orden_id, persona).status_code == 200
    assert _asignar(api, datos["cocinero"], orden_id, persona).status_code == 200
    s = S()
    n = len(s.execute(select(AuditLog).where(
        AuditLog.accion == "ORDEN_RESPONSABLE_COCINA_ASIGNADO",
        AuditLog.entidad_id == str(orden_id),
    )).scalars().all())
    s.close()
    assert n == 1


# ---------------------------------------------------------------------------
# LISTO y ENTREGADO exigen responsable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["listo", "entregado"])
def test_listo_o_entregado_sin_responsable_da_409(api, datos, S, estado):
    orden_id = _orden(S, datos["a"], OrdenEstado.PREPARANDO)
    r = _status(api, datos["cocinero"] if estado == "listo" else datos["repartidor"], orden_id, estado)
    assert r.status_code == 409
    assert "responsable" in r.json()["detail"]
    assert _orden_bd(S, orden_id).estado == OrdenEstado.PREPARANDO


def test_listo_con_responsable_da_200(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos["cocinero"], orden_id, persona).status_code == 200
    r = _status(api, datos["cocinero"], orden_id, "listo")
    assert r.status_code == 200
    assert _orden_bd(S, orden_id).estado == OrdenEstado.LISTO


def test_orden_anterior_a_la_migracion_se_cierra_sin_responsable(api, datos, S):
    orden_id = _orden(S, datos["a"], exige=False)
    assert _status(api, datos["cocinero"], orden_id, "listo").status_code == 200
    assert _status(api, datos["repartidor"], orden_id, "entregado").status_code == 200


def test_orden_nueva_nace_exigiendo_responsable(S, datos):
    s = S()
    o = Orden(punto_id=datos["a"], numero_orden=f"CO-{uuid.uuid4().hex[:12]}", total=1, cliente_nombre="x")
    s.add(o)
    s.commit()
    assert o.exige_responsable_cocina is True
    s.close()


def test_listado_de_ordenes_trae_responsable_y_hora(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos["cocinero"], orden_id, persona).status_code == 200
    lista = api.get("/api/ordenes/", headers=_auth(datos["cocinero"])).json()
    fila = next(o for o in lista if o["id"] == orden_id)
    assert fila["responsable_cocina"]["id"] == persona
    assert fila["responsable_cocina"]["nombre"].startswith("Cocinero ")
    assert fila["en_preparacion_at"] is not None
    assert fila["exige_responsable_cocina"] is True


# ---------------------------------------------------------------------------
# CRUD de personal
# ---------------------------------------------------------------------------

URL = "/api/config/personal-cocina"


def test_resp_tienda_crea_en_su_tienda(api, datos):
    r = api.post(URL, json={"nombre": "  María   López  "}, headers=_auth(datos["resp_tienda"]))
    assert r.status_code == 201, r.text
    assert r.json()["nombre"] == "María López"
    assert r.json()["punto_id"] == datos["a"]
    assert r.json()["activo"] is True


def test_resp_tienda_no_crea_en_otra_tienda(api, datos):
    r = api.post(URL, json={"nombre": "Intruso", "punto_id": datos["b"]}, headers=_auth(datos["resp_tienda"]))
    assert r.status_code == 403


def test_gerencia_crea_indicando_tienda_y_sin_ella_da_400(api, datos):
    h = _auth(datos["gerente_general"])
    assert api.post(URL, json={"nombre": f"Gerencia {uuid.uuid4().hex[:6]}"}, headers=h).status_code == 400
    r = api.post(URL, json={"nombre": f"Gerencia {uuid.uuid4().hex[:6]}", "punto_id": datos["b"]}, headers=h)
    assert r.status_code == 201
    assert r.json()["punto_id"] == datos["b"]


@pytest.mark.parametrize("rol", ["cocinero", "gerente_punto", "repartidor", "tomador_orden"])
def test_otros_roles_no_administran_personal(api, datos, S, rol):
    h = _auth(datos[rol])
    assert api.post(URL, json={"nombre": "No"}, headers=h).status_code == 403
    persona = _persona(S, datos["a"])
    assert api.patch(f"{URL}/{persona}", json={"activo": False}, headers=h).status_code == 403


def test_nombre_repetido_en_la_tienda_da_400(api, datos):
    nombre = f"Repetido {uuid.uuid4().hex[:6]}"
    h = _auth(datos["resp_tienda"])
    assert api.post(URL, json={"nombre": nombre}, headers=h).status_code == 201
    assert api.post(URL, json={"nombre": nombre.upper()}, headers=h).status_code == 400


def test_nombre_vacio_da_422(api, datos):
    assert api.post(URL, json={"nombre": "   "}, headers=_auth(datos["resp_tienda"])).status_code == 422


def test_patch_renombra_desactiva_y_reactiva_con_auditoria(api, datos, S):
    persona = _persona(S, datos["a"])
    h = _auth(datos["resp_tienda"])
    nuevo = f"Renombrado {uuid.uuid4().hex[:6]}"
    r = api.patch(f"{URL}/{persona}", json={"nombre": nuevo}, headers=h)
    assert r.status_code == 200 and r.json()["nombre"] == nuevo
    assert api.patch(f"{URL}/{persona}", json={"activo": False}, headers=h).json()["activo"] is False
    assert api.patch(f"{URL}/{persona}", json={"activo": True}, headers=h).json()["activo"] is True
    s = S()
    filas = s.execute(select(AuditLog).where(
        AuditLog.accion == "PERSONAL_COCINA_ACTUALIZADO", AuditLog.entidad_id == str(persona),
    ).order_by(AuditLog.id)).scalars().all()
    s.close()
    assert len(filas) == 3
    assert filas[1].detalle["antes"]["activo"] is True and filas[1].detalle["despues"]["activo"] is False


def test_renombrar_no_cambia_el_id_guardado_en_la_orden(api, datos, S):
    persona = _persona(S, datos["a"])
    orden_id = _orden(S, datos["a"])
    assert _asignar(api, datos["cocinero"], orden_id, persona).status_code == 200
    nuevo = f"Nombre nuevo {uuid.uuid4().hex[:6]}"
    assert api.patch(f"{URL}/{persona}", json={"nombre": nuevo}, headers=_auth(datos["resp_tienda"])).status_code == 200
    lista = api.get("/api/ordenes/", headers=_auth(datos["cocinero"])).json()
    fila = next(o for o in lista if o["id"] == orden_id)
    assert fila["responsable_cocina"] == {"id": persona, "nombre": nuevo}


def test_patch_de_otra_tienda_da_403(api, datos, S):
    de_b = _persona(S, datos["b"])
    r = api.patch(f"{URL}/{de_b}", json={"activo": False}, headers=_auth(datos["resp_tienda"]))
    assert r.status_code == 403


def test_no_hay_delete(api, datos, S):
    persona = _persona(S, datos["a"])
    r = api.delete(f"{URL}/{persona}", headers=_auth(datos["admin"]))
    assert r.status_code == 405


def test_cocina_lista_solo_activos_y_resp_ve_inactivos(api, datos, S):
    activo, inactivo = _persona(S, datos["a"]), _persona(S, datos["a"], activo=False)
    ids_cocina = {p["id"] for p in api.get(
        URL, params={"incluir_inactivos": True}, headers=_auth(datos["cocinero"])).json()}
    assert activo in ids_cocina and inactivo not in ids_cocina
    ids_resp = {p["id"] for p in api.get(
        URL, params={"incluir_inactivos": True}, headers=_auth(datos["resp_tienda"])).json()}
    assert {activo, inactivo} <= ids_resp


def test_listado_solo_de_la_propia_tienda(api, datos, S):
    de_b = _persona(S, datos["b"])
    ids = {p["id"] for p in api.get(URL, headers=_auth(datos["resp_tienda"])).json()}
    assert de_b not in ids
    assert api.get(URL, params={"punto_id": datos["b"]}, headers=_auth(datos["resp_tienda"])).status_code == 403
