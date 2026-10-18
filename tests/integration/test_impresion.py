"""Impresión por agente de tienda + apertura de cajón (docs/DISENO_IMPRESION.md).

Todo corre contra la BD de prueba y nunca habla con una impresora: el
"agente" aquí son llamadas HTTP con su token a los endpoints del backend.
El agente real (tools/agente_impresion) se prueba aparte con un transporte
mock (tests/unit/test_agente_impresion.py).

Cada grupo de pruebas usa su propia tienda para que la cola de trabajos de
una no interfiera con otra (el agente se lleva TODOS los pendientes de su
tienda en cada poll).
"""

import hashlib
import uuid
from datetime import datetime, timedelta

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
    OrdenItem,
    PuntoVenta,
    TokenAgente,
    TrabajoImpresion,
    Usuario,
    UserRol,
)

ROLES_TODOS = [r.value for r in UserRol]
ROLES_TICKET = {"tomador_orden", "resp_tienda", "gerente_punto", "gerente_general", "admin"}
ROLES_CAJON = {"resp_tienda", "gerente_punto", "gerente_general", "admin"}
ROLES_TOKEN = {"gerente_general", "admin"}
# Roles que en la BD pueden existir sin tienda; aquí todos llevan tienda
# salvo gerente_central, para ejercitar también ese caso.
ROLES_SIN_TIENDA = {"gerente_central"}


def _auth(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


def _agente(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ctx(engine):
    Session = sessionmaker(bind=engine)
    s = Session()

    empresa = Empresa(nombre="Impresion Test", nit=f"TEST-IMP-{uuid.uuid4().hex[:6]}")
    s.add(empresa)
    s.flush()

    def tienda(nombre, impresora=True, cajon=True):
        p = PuntoVenta(
            empresa_id=empresa.id,
            nombre=nombre,
            impresora_activa=impresora,
            cajon_activo=cajon,
        )
        s.add(p)
        s.flush()
        return p

    tiendas = {
        "matriz": tienda("IMP Matriz"),           # matriz de roles
        "token": tienda("IMP Token"),             # matriz de regenerar token
        "agente": tienda("IMP Agente"),           # flujo del agente
        "agente2": tienda("IMP Agente 2"),        # otra tienda con agente
        "sin_cajon": tienda("IMP Sin cajon", cajon=False),
        "sin_impresora": tienda("IMP Sin impresora", impresora=False, cajon=False),
    }

    def usuario(rol: str, punto):
        u = Usuario(
            empresa_id=empresa.id,
            punto_id=None if rol in ROLES_SIN_TIENDA else punto.id,
            username=f"imp_{rol}_{punto.id}_{uuid.uuid4().hex[:4]}",
            email=f"imp_{rol}_{uuid.uuid4().hex[:8]}@test.gt",
            password_hash=hash_password("secreta123"),
            rol=UserRol(rol),
        )
        s.add(u)
        s.flush()
        return {
            "user_id": u.id,
            "username": u.username,
            "punto_id": u.punto_id,
            "rol": u.rol.value,
            "empresa_id": u.empresa_id,
        }

    out = {"tiendas": {k: v.id for k, v in tiendas.items()}, "empresa_id": empresa.id}
    out["roles"] = {rol: usuario(rol, tiendas["matriz"]) for rol in ROLES_TODOS}
    for clave in ("agente", "agente2", "sin_cajon", "sin_impresora"):
        out[f"resp_{clave}"] = usuario("resp_tienda", tiendas[clave])
    out["tomador_agente"] = usuario("tomador_orden", tiendas["agente"])
    out["admin"] = out["roles"]["admin"]
    s.commit()
    s.close()
    yield out


@pytest.fixture
def S(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _insertar_orden(engine, punto_id, *, metodo_pago=MetodoPago.EFECTIVO,
                    estado_cobro="pendiente_recibir", total=100.0) -> int:
    Session = sessionmaker(bind=engine)
    s = Session()
    o = Orden(
        punto_id=punto_id,
        numero_orden=f"TEST-{uuid.uuid4().hex[:12]}",
        metodo_pago=metodo_pago,
        total=total,
        dinero_recibido=total,
        vuelto=0,
        estado=OrdenEstado.PENDIENTE,
        estado_cobro=estado_cobro,
    )
    s.add(o)
    s.flush()
    s.add(OrdenItem(orden_id=o.id, producto="1/4 Pollo", cantidad=1,
                    precio_unitario=total, subtotal=total))
    s.commit()
    orden_id = o.id
    s.close()
    return orden_id


def _insertar_trabajo(engine, punto_id, solicitado_por, *, tipo="ticket", estado="pendiente",
                      orden_id=None, tomado_at=None, created_at=None) -> int:
    Session = sessionmaker(bind=engine)
    s = Session()
    t = TrabajoImpresion(
        punto_id=punto_id, tipo=tipo, payload={}, estado=estado,
        solicitado_por=solicitado_por, orden_id=orden_id, tomado_at=tomado_at,
        motivo="prueba manual" if tipo == "abrir_cajon" else None,
        created_at=created_at or datetime.utcnow(),
    )
    s.add(t)
    s.commit()
    tid = t.id
    s.close()
    return tid


def _regenerar_token(api, ctx, tienda: str) -> str:
    r = api.post(
        f"/api/puntos-venta/{ctx['tiendas'][tienda]}/regenerar-token-agente",
        headers=_auth(ctx["admin"]),
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _confirmar(api, usuario, orden_id):
    return api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(usuario),
    )


def _cajones_de_orden(S, orden_id):
    return S.execute(
        select(TrabajoImpresion).where(
            TrabajoImpresion.orden_id == orden_id, TrabajoImpresion.tipo == "abrir_cajon"
        )
    ).scalars().all()


@pytest.fixture(scope="module")
def token_agente(api, ctx):
    return _regenerar_token(api, ctx, "agente")


def _vaciar_cola(api, token):
    """Deja la cola de la tienda del agente sin pendientes (los marca ok)."""
    for t in api.get("/api/impresion/agente/pendientes", headers=_agente(token)).json():
        api.post(f"/api/impresion/agente/trabajos/{t['id']}/resultado",
                 json={"estado": "ok"}, headers=_agente(token))


# ---------------------------------------------------------------------------
# Matriz de roles contra cada endpoint nuevo
# ---------------------------------------------------------------------------


def _esperado(rol, permitidos, ok):
    return ok if rol in permitidos else 403


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_ticket(api, ctx, engine, rol):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["matriz"], estado_cobro="cobrada")
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_TICKET, 201), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_abrir_cajon(api, ctx, rol):
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "faltó cambio"},
                 headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_CAJON, 201), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_listar_trabajos(api, ctx, rol):
    r = api.get("/api/impresion/trabajos", headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_TICKET, 200), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_reintentar(api, ctx, engine, rol):
    """Trabajo TICKET en error creado por resp_tienda: lo reintenta la
    gerencia de la tienda; el tomador_orden no (no es suyo)."""
    tid = _insertar_trabajo(engine, ctx["tiendas"]["matriz"],
                            ctx["roles"]["resp_tienda"]["user_id"], estado="error")
    r = api.post(f"/api/impresion/trabajos/{tid}/reintentar", headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_CAJON, 200), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_estado_agente(api, ctx, rol):
    r = api.get("/api/impresion/agente/estado", headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_CAJON, 200), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
def test_matriz_regenerar_token(api, ctx, rol):
    r = api.post(f"/api/puntos-venta/{ctx['tiendas']['token']}/regenerar-token-agente",
                 headers=_auth(ctx["roles"][rol]))
    assert r.status_code == _esperado(rol, ROLES_TOKEN, 200), r.text


@pytest.mark.parametrize("rol", ROLES_TODOS)
@pytest.mark.parametrize("metodo,ruta", [
    ("get", "/api/impresion/agente/pendientes"),
    ("post", "/api/impresion/agente/trabajos/1/resultado"),
])
def test_matriz_endpoints_agente_rechazan_jwt_de_usuario(api, ctx, rol, metodo, ruta):
    """Ningún rol de usuario entra a los endpoints del agente: su JWT no es
    un token de agente."""
    kwargs = {"headers": _auth(ctx["roles"][rol])}
    if metodo == "post":
        kwargs["json"] = {"estado": "ok"}
    r = getattr(api, metodo)(ruta, **kwargs)
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# Abrir cajón manual
# ---------------------------------------------------------------------------


def test_tomador_abrir_cajon_403_y_audit_log(api, ctx, S):
    tomador = ctx["roles"]["tomador_orden"]
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "quiero abrir"},
                 headers=_auth(tomador))
    assert r.status_code == 403
    logs = S.execute(
        select(AuditLog).where(
            AuditLog.accion == "INTENTO_ABRIR_CAJON_DENEGADO",
            AuditLog.usuario_id == tomador["user_id"],
        )
    ).scalars().all()
    assert len(logs) >= 1
    assert logs[-1].punto_id == ctx["tiendas"]["matriz"]
    # Y no se encoló nada a nombre del tomador.
    assert not S.execute(
        select(TrabajoImpresion).where(TrabajoImpresion.solicitado_por == tomador["user_id"],
                                       TrabajoImpresion.tipo == "abrir_cajon")
    ).first()


def test_tomador_con_motivo_corto_igual_recibe_403(api, ctx):
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "x"},
                 headers=_auth(ctx["roles"]["tomador_orden"]))
    assert r.status_code == 403


def test_abrir_cajon_motivo_menor_a_5_caracteres(api, ctx):
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "  abc  "},
                 headers=_auth(ctx["roles"]["resp_tienda"]))
    assert r.status_code == 422


def test_abrir_cajon_manual_registra_audit_y_motivo(api, ctx, S):
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "cambio de billete"},
                 headers=_auth(ctx["roles"]["gerente_punto"]))
    assert r.status_code == 201
    body = r.json()
    assert body["tipo"] == "abrir_cajon" and body["estado"] == "pendiente"
    assert body["motivo"] == "cambio de billete" and body["orden_id"] is None
    log = S.execute(
        select(AuditLog).where(AuditLog.accion == "ABRIR_CAJON_MANUAL",
                               AuditLog.entidad_id == str(body["id"]))
    ).scalar_one()
    assert log.usuario_id == ctx["roles"]["gerente_punto"]["user_id"]


def test_abrir_cajon_tienda_con_cajon_inactivo_409(api, ctx):
    r = api.post("/api/impresion/abrir-cajon", json={"motivo": "cambio de billete"},
                 headers=_auth(ctx["resp_sin_cajon"]))
    assert r.status_code == 409


def test_resp_tienda_no_abre_cajon_de_otra_tienda(api, ctx):
    r = api.post("/api/impresion/abrir-cajon",
                 json={"motivo": "cambio de billete", "punto_id": ctx["tiendas"]["agente"]},
                 headers=_auth(ctx["roles"]["resp_tienda"]))
    assert r.status_code == 403


def test_gerente_punto_sigue_sin_poder_abrir_caja_financiera(api, ctx):
    """El permiso de cajón no amplía _ROLES_TIENDA (decisión 1 de §11)."""
    r = api.post("/api/caja/abrir", json={"fondo_inicial": 100},
                 headers=_auth(ctx["roles"]["gerente_punto"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Token del agente
# ---------------------------------------------------------------------------


def test_agente_sin_token_401(api):
    assert api.get("/api/impresion/agente/pendientes").status_code == 401


def test_agente_token_invalido_401(api):
    r = api.get("/api/impresion/agente/pendientes", headers=_agente("no-es-un-token"))
    assert r.status_code == 401


def test_regenerar_token_revoca_el_viejo_y_el_nuevo_funciona(api, ctx, S):
    viejo = _regenerar_token(api, ctx, "agente2")
    assert api.get("/api/impresion/agente/pendientes", headers=_agente(viejo)).status_code == 200

    r = api.post(f"/api/puntos-venta/{ctx['tiendas']['agente2']}/regenerar-token-agente",
                 headers=_auth(ctx["admin"]))
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    nuevo = r.json()["token"]
    assert nuevo != viejo

    # Revocado -> 401; nuevo -> 200.
    assert api.get("/api/impresion/agente/pendientes", headers=_agente(viejo)).status_code == 401
    assert api.get("/api/impresion/agente/pendientes", headers=_agente(nuevo)).status_code == 200

    tokens = S.execute(
        select(TokenAgente).where(TokenAgente.punto_id == ctx["tiendas"]["agente2"])
        .order_by(TokenAgente.id)
    ).scalars().all()
    assert [t.activo for t in tokens] == [False, True]
    assert tokens[0].revocado_at is not None
    # En la BD solo queda el sha256, nunca el token en claro.
    assert tokens[1].token_hash == hashlib.sha256(nuevo.encode()).hexdigest()
    assert all(t.token_hash not in (viejo, nuevo) for t in tokens)
    # Y tampoco en el audit_log.
    for log in S.execute(
        select(AuditLog).where(AuditLog.accion == "REGENERAR_TOKEN_AGENTE",
                               AuditLog.punto_id == ctx["tiendas"]["agente2"])
    ).scalars():
        assert viejo not in str(log.detalle) and nuevo not in str(log.detalle)


def test_token_de_una_tienda_no_ve_trabajos_de_otra(api, ctx, engine, token_agente):
    otro = _regenerar_token(api, ctx, "agente2")
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"])
    ids = [t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                    headers=_agente(otro)).json()]
    assert tid not in ids
    # Tampoco puede reportar su resultado: 404.
    r = api.post(f"/api/impresion/agente/trabajos/{tid}/resultado",
                 json={"estado": "ok"}, headers=_agente(otro))
    assert r.status_code == 404
    _vaciar_cola(api, token_agente)


def test_heartbeat_estado_agente(api, ctx, S, token_agente):
    api.get("/api/impresion/agente/pendientes", headers=_agente(token_agente))
    r = api.get("/api/impresion/agente/estado", headers=_auth(ctx["resp_agente"]))
    assert r.status_code == 200
    assert r.json()["conectado"] is True and r.json()["tiene_token"] is True

    tok = S.execute(select(TokenAgente).where(
        TokenAgente.punto_id == ctx["tiendas"]["agente"], TokenAgente.activo.is_(True))
    ).scalar_one()
    tok.ultima_conexion_at = datetime.utcnow() - timedelta(seconds=31)
    S.commit()
    assert api.get("/api/impresion/agente/estado",
                   headers=_auth(ctx["resp_agente"])).json()["conectado"] is False


# ---------------------------------------------------------------------------
# Disparador en confirmar-cobro
# ---------------------------------------------------------------------------


def test_confirmar_cobro_crea_un_abrir_cajon(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    r = _confirmar(api, ctx["resp_agente"], orden_id)
    assert r.status_code == 200
    cajones = _cajones_de_orden(S, orden_id)
    assert len(cajones) == 1
    c = cajones[0]
    assert c.estado == "pendiente" and c.motivo == "cobro_efectivo"
    assert c.solicitado_por == ctx["resp_agente"]["user_id"]
    assert S.execute(select(AuditLog).where(
        AuditLog.accion == "ABRIR_CAJON_AUTOMATICO", AuditLog.entidad_id == str(c.id))
    ).scalar_one()


def test_confirmar_cobro_dos_veces_400_y_un_solo_abrir_cajon(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    assert _confirmar(api, ctx["resp_agente"], orden_id).status_code == 200
    r2 = _confirmar(api, ctx["resp_agente"], orden_id)
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Esta orden ya fue cobrada"
    assert len(_cajones_de_orden(S, orden_id)) == 1


def test_confirmar_cobro_con_cajon_inactivo_no_crea_abrir_cajon(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["sin_cajon"])
    r = _confirmar(api, ctx["resp_sin_cajon"], orden_id)
    assert r.status_code == 200
    assert r.json()["estado_cobro"] == "cobrada"
    assert _cajones_de_orden(S, orden_id) == []


def test_confirmar_cobro_no_depende_de_la_impresion(api, ctx, engine, S, monkeypatch):
    """§8: si encolar el ABRIR_CAJON revienta, el cobro se confirma igual."""
    import foodops.domain.impresion as impresion

    def explota(*a, **k):
        raise RuntimeError("fallo simulado al encolar")

    monkeypatch.setattr(impresion, "registrar_auditoria", explota)
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    r = _confirmar(api, ctx["resp_agente"], orden_id)
    assert r.status_code == 200, r.text
    assert r.json()["estado_cobro"] == "cobrada"
    S.expire_all()
    assert S.get(Orden, orden_id).estado_cobro == "cobrada"
    assert _cajones_de_orden(S, orden_id) == []
    # El audit propio de confirmar-cobro sí quedó.
    assert S.execute(select(AuditLog).where(
        AuditLog.accion == "CONFIRMAR_COBRO_EFECTIVO", AuditLog.entidad_id == str(orden_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------


def test_reimprimir_no_crea_abrir_cajon(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    assert _confirmar(api, ctx["resp_agente"], orden_id).status_code == 200
    for _ in range(3):
        r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                     headers=_auth(ctx["resp_agente"]))
        assert r.status_code == 201 and r.json()["tipo"] == "ticket"
    tickets = S.execute(select(TrabajoImpresion).where(
        TrabajoImpresion.orden_id == orden_id, TrabajoImpresion.tipo == "ticket")
    ).scalars().all()
    assert len(tickets) == 3
    # Sigue habiendo exactamente el ABRIR_CAJON de la confirmación.
    assert len(_cajones_de_orden(S, orden_id)) == 1


def test_ticket_de_orden_con_tarjeta_nunca_crea_abrir_cajon(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"],
                               metodo_pago=MetodoPago.TARJETA, estado_cobro="cobrada")
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["tomador_agente"]))
    assert r.status_code == 201
    assert _cajones_de_orden(S, orden_id) == []


def test_ticket_payload_es_json_no_html(api, ctx, engine, S):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"], estado_cobro="cobrada")
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["resp_agente"]))
    t = S.get(TrabajoImpresion, r.json()["id"])
    assert t.payload["version"] == 1
    assert t.payload["orden"]["id"] == orden_id
    assert t.payload["orden"]["items"][0]["producto"] == "1/4 Pollo"
    assert t.payload["orden"]["punto_nombre"] == "IMP Agente"
    assert "<" not in str(t.payload)


def test_ticket_tienda_sin_impresora_409(api, ctx, engine):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["sin_impresora"], estado_cobro="cobrada")
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["resp_sin_impresora"]))
    assert r.status_code == 409


def test_ticket_de_orden_de_otra_tienda_403(api, ctx, engine):
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"], estado_cobro="cobrada")
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["roles"]["tomador_orden"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Regla de venta (§8) y flujo del agente
# ---------------------------------------------------------------------------


def test_agente_apagado_venta_guardada_y_trabajos_pendientes(api, ctx, S, token_agente):
    """Sin que el agente haga poll: la orden se crea, se confirma y se encola
    todo en PENDIENTE; nada se bloquea."""
    _vaciar_cola(api, token_agente)
    r = api.post(
        "/api/ordenes/",
        json={"metodo_pago": "efectivo", "dinero_recibido": 100, "vuelto": 15,
              "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 85}]},
        headers=_auth(ctx["tomador_agente"]),
    )
    assert r.status_code == 200, r.text
    orden_id = r.json()["id"]

    assert _confirmar(api, ctx["resp_agente"], orden_id).status_code == 200
    r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                 headers=_auth(ctx["resp_agente"]))
    assert r.status_code == 201

    S.expire_all()
    assert S.get(Orden, orden_id).estado_cobro == "cobrada"
    trabajos = S.execute(select(TrabajoImpresion).where(TrabajoImpresion.orden_id == orden_id)
                         ).scalars().all()
    assert sorted(t.tipo for t in trabajos) == ["abrir_cajon", "ticket"]
    assert all(t.estado == "pendiente" and t.tomado_at is None for t in trabajos)

    # Cuando el agente vuelve, los recoge.
    ids = {t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                    headers=_agente(token_agente)).json()}
    assert {t.id for t in trabajos} <= ids
    _vaciar_cola(api, token_agente)


@pytest.mark.parametrize("res_ticket,res_cajon", [("error", "ok"), ("ok", "error")])
def test_cada_trabajo_reporta_su_propio_estado(api, ctx, engine, S, token_agente,
                                              res_ticket, res_cajon):
    _vaciar_cola(api, token_agente)
    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    assert _confirmar(api, ctx["resp_agente"], orden_id).status_code == 200
    api.post("/api/impresion/ticket", json={"orden_id": orden_id},
             headers=_auth(ctx["resp_agente"]))

    pendientes = api.get("/api/impresion/agente/pendientes", headers=_agente(token_agente)).json()
    por_tipo = {t["tipo"]: t for t in pendientes if t["orden_id"] == orden_id}
    assert set(por_tipo) == {"ticket", "abrir_cajon"}
    assert all(t["estado"] == "imprimiendo" for t in por_tipo.values())

    for tipo, res in (("ticket", res_ticket), ("abrir_cajon", res_cajon)):
        body = {"estado": res}
        if res == "error":
            body["error"] = "sin papel"
        r = api.post(f"/api/impresion/agente/trabajos/{por_tipo[tipo]['id']}/resultado",
                     json=body, headers=_agente(token_agente))
        assert r.status_code == 200

    estados = {t["tipo"]: t for t in api.get(
        f"/api/impresion/trabajos?orden_id={orden_id}", headers=_auth(ctx["resp_agente"])
    ).json()}
    assert estados["ticket"]["estado"] == res_ticket
    assert estados["abrir_cajon"]["estado"] == res_cajon
    fallido = estados["ticket"] if res_ticket == "error" else estados["abrir_cajon"]
    assert fallido["error"] == "sin papel"
    assert S.execute(select(AuditLog).where(
        AuditLog.accion == "FALLO_IMPRESION", AuditLog.entidad_id == str(fallido["id"]))
    ).scalar_one()


def test_resultado_dos_veces_409(api, ctx, engine, token_agente):
    _vaciar_cola(api, token_agente)
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"])
    api.get("/api/impresion/agente/pendientes", headers=_agente(token_agente))
    url = f"/api/impresion/agente/trabajos/{tid}/resultado"
    assert api.post(url, json={"estado": "ok"}, headers=_agente(token_agente)).status_code == 200
    assert api.post(url, json={"estado": "ok"}, headers=_agente(token_agente)).status_code == 409


def test_timeout_30s_reencola_imprimiendo(api, ctx, engine, token_agente):
    _vaciar_cola(api, token_agente)
    resp = ctx["resp_agente"]["user_id"]
    tienda = ctx["tiendas"]["agente"]
    vencido = _insertar_trabajo(engine, tienda, resp, estado="imprimiendo",
                                tomado_at=datetime.utcnow() - timedelta(seconds=31))
    reciente = _insertar_trabajo(engine, tienda, resp, estado="imprimiendo",
                                 tomado_at=datetime.utcnow() - timedelta(seconds=10))

    ids = [t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                    headers=_agente(token_agente)).json()]
    assert vencido in ids
    assert reciente not in ids
    # Y el vencido vuelve a quedar tomado (no se entrega dos veces seguidas).
    ids2 = [t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                     headers=_agente(token_agente)).json()]
    assert vencido not in ids2
    for tid in (vencido, reciente):
        api.post(f"/api/impresion/agente/trabajos/{tid}/resultado",
                 json={"estado": "ok"}, headers=_agente(token_agente))


# ---------------------------------------------------------------------------
# Reintentar
# ---------------------------------------------------------------------------


def test_reintentar_vuelve_a_pendiente_mismo_id(api, ctx, engine, S):
    tid = _insertar_trabajo(engine, ctx["tiendas"]["matriz"],
                            ctx["roles"]["tomador_orden"]["user_id"], estado="error")
    # El tomador sí reintenta su propio ticket.
    r = api.post(f"/api/impresion/trabajos/{tid}/reintentar",
                 headers=_auth(ctx["roles"]["tomador_orden"]))
    assert r.status_code == 200
    assert r.json()["id"] == tid and r.json()["estado"] == "pendiente"
    assert r.json()["error"] is None
    # Ya no está en error: un segundo reintento es 409.
    r2 = api.post(f"/api/impresion/trabajos/{tid}/reintentar",
                  headers=_auth(ctx["roles"]["tomador_orden"]))
    assert r2.status_code == 409


def test_tomador_no_reintenta_abrir_cajon(api, ctx, engine):
    tid = _insertar_trabajo(engine, ctx["tiendas"]["matriz"],
                            ctx["roles"]["tomador_orden"]["user_id"],
                            tipo="abrir_cajon", estado="error")
    r = api.post(f"/api/impresion/trabajos/{tid}/reintentar",
                 headers=_auth(ctx["roles"]["tomador_orden"]))
    assert r.status_code == 403


def test_reintentar_trabajo_de_otra_tienda_403(api, ctx, engine):
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"],
                            ctx["resp_agente"]["user_id"], estado="error")
    r = api.post(f"/api/impresion/trabajos/{tid}/reintentar",
                 headers=_auth(ctx["roles"]["resp_tienda"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Índice único parcial: un ABRIR_CAJON por orden, TICKET sin límite
# ---------------------------------------------------------------------------


def test_indice_cajon_es_parcial(engine):
    from sqlalchemy import text

    with engine.connect() as c:
        indexdef = c.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'ux_trabajos_impresion_cajon_por_orden'"
        )).scalar_one()
    assert "UNIQUE" in indexdef
    assert "WHERE" in indexdef and "'abrir_cajon'" in indexdef


def test_orden_admite_ticket_y_reimpresiones_pero_un_solo_abrir_cajon(api, ctx, engine, S):
    from sqlalchemy.exc import IntegrityError

    orden_id = _insertar_orden(engine, ctx["tiendas"]["agente"])
    assert _confirmar(api, ctx["resp_agente"], orden_id).status_code == 200
    for _ in range(4):  # ticket + 3 reimpresiones
        r = api.post("/api/impresion/ticket", json={"orden_id": orden_id},
                     headers=_auth(ctx["resp_agente"]))
        assert r.status_code == 201
    tipos = [t.tipo for t in S.execute(
        select(TrabajoImpresion).where(TrabajoImpresion.orden_id == orden_id)).scalars()]
    assert tipos.count("ticket") == 4 and tipos.count("abrir_cajon") == 1

    # Un segundo ABRIR_CAJON para la misma orden lo rechaza la propia BD.
    with pytest.raises(IntegrityError):
        _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                          tipo="abrir_cajon", orden_id=orden_id)

    # Los ABRIR_CAJON manuales (orden_id NULL) no chocan entre sí.
    for _ in range(2):
        _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                          tipo="abrir_cajon", estado="ok")


# ---------------------------------------------------------------------------
# Caducidad del ABRIR_CAJON (120s)
# ---------------------------------------------------------------------------


class _ImpresoraMock:
    def __init__(self):
        self.enviados = []

    def enviar(self, datos):
        self.enviados.append(datos)


def _agente_real(api, token, tmp_path):
    """Lógica real del agente (tools/agente_impresion) hablando con el
    backend por TestClient, con impresora mock."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from agente_impresion.agente import Agente, Config

    h = _agente(token)

    class ApiTestClient:
        def pendientes(self):
            r = api.get("/api/impresion/agente/pendientes", headers=h)
            assert r.status_code == 200
            return r.json()

        def reportar(self, tid, estado, error=None):
            body = {"estado": estado, **({"error": error} if error else {})}
            assert api.post(f"/api/impresion/agente/trabajos/{tid}/resultado",
                            json=body, headers=h).status_code == 200

    impresora = _ImpresoraMock()
    config = Config(api_url="http://test", token=token, impresora_ip="127.0.0.1",
                    archivo_impresos=str(tmp_path / "impresos.json"))
    return Agente(config, ApiTestClient(), impresora), impresora


PULSO = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])


def test_cajon_de_hace_5_minutos_caduca_y_no_envia_pulso(api, ctx, engine, S, token_agente,
                                                          tmp_path):
    _vaciar_cola(api, token_agente)
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                            tipo="abrir_cajon",
                            created_at=datetime.utcnow() - timedelta(minutes=5))
    agente, impresora = _agente_real(api, token_agente, tmp_path)
    agente.ciclo()

    assert not any(PULSO in d for d in impresora.enviados)
    t = S.get(TrabajoImpresion, tid)
    assert t.estado == "error" and t.error == "caducado" and t.completado_at is not None
    assert S.execute(select(AuditLog).where(
        AuditLog.accion == "ABRIR_CAJON_CADUCADO", AuditLog.entidad_id == str(tid))
    ).scalar_one()


def test_cajon_reciente_si_se_ejecuta(api, ctx, engine, S, token_agente, tmp_path):
    _vaciar_cola(api, token_agente)
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                            tipo="abrir_cajon",
                            created_at=datetime.utcnow() - timedelta(seconds=60))
    agente, impresora = _agente_real(api, token_agente, tmp_path)
    agente.ciclo()
    assert impresora.enviados == [b"\x1b@" + PULSO]
    assert S.get(TrabajoImpresion, tid).estado == "ok"


def test_cajon_imprimiendo_vencido_y_caducado_no_se_reentrega(api, ctx, engine, S, token_agente):
    """Agente caído a mitad: a los 30s se reentregaría, pero si ya pasaron
    120s desde que se creó, caduca en vez de abrir el cajón tarde."""
    _vaciar_cola(api, token_agente)
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                            tipo="abrir_cajon", estado="imprimiendo",
                            created_at=datetime.utcnow() - timedelta(seconds=150),
                            tomado_at=datetime.utcnow() - timedelta(seconds=40))
    ids = [t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                    headers=_agente(token_agente)).json()]
    assert tid not in ids
    t = S.get(TrabajoImpresion, tid)
    assert t.estado == "error" and t.error == "caducado"


def test_ticket_viejo_no_caduca(api, ctx, engine, S, token_agente):
    _vaciar_cola(api, token_agente)
    tid = _insertar_trabajo(engine, ctx["tiendas"]["agente"], ctx["resp_agente"]["user_id"],
                            created_at=datetime.utcnow() - timedelta(hours=3))
    ids = [t["id"] for t in api.get("/api/impresion/agente/pendientes",
                                    headers=_agente(token_agente)).json()]
    assert tid in ids
    _vaciar_cola(api, token_agente)


def test_reintentar_cajon_caducado_409(api, ctx, engine):
    tid = _insertar_trabajo(engine, ctx["tiendas"]["matriz"],
                            ctx["roles"]["resp_tienda"]["user_id"], tipo="abrir_cajon",
                            estado="error", created_at=datetime.utcnow() - timedelta(minutes=5))
    r = api.post(f"/api/impresion/trabajos/{tid}/reintentar",
                 headers=_auth(ctx["roles"]["resp_tienda"]))
    assert r.status_code == 409
