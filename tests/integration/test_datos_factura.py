"""Fase 1 de facturación: nombre obligatorio al cobrar y datos fiscales.

Cubre la matriz de roles de PUT /api/ordenes/{id}/datos-factura y de
POST /api/ordenes/{id}/datos-factura/marcar-generada, las reglas de bloqueo,
la auditoría (antes/después con NIT enmascarado) y el formato del NIT.

Como en test_cobro_efectivo.py, casi todas las órdenes se insertan directo en
la BD con numero_orden por UUID: POST /api/ordenes/ genera el número con
resolución de segundos y dos órdenes de la misma tienda en el mismo segundo
chocan. Solo la prueba de nombre normalizado usa el endpoint real, en su
propia tienda.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.api.router_impresion import ROLES_IMPRESION_TICKET, _payload_ticket
from foodops.api.router_ordenes import _ROLES_CAPTURA_FACTURA, _ROLES_CONFIRMAR_COBRO
from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import (
    AuditLog,
    DatosFacturacion,
    Empresa,
    MetodoPago,
    Orden,
    OrdenEstado,
    PuntoVenta,
    Usuario,
    UserRol,
)
from foodops.domain.schemas import normalizar_nit

DATOS_OK = {
    "requiere_factura": True,
    "nit": "1234567-8",
    "nombre_fiscal": "Cliente Fiscal S.A.",
    "direccion_fiscal": "Ciudad",
}


def _auth(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def ctx(S):
    s = S()
    empresa = Empresa(nombre="Facturacion Test", nit="TEST-FAC-1")
    s.add(empresa)
    s.flush()
    tienda_a = PuntoVenta(empresa_id=empresa.id, nombre="Tienda FAC A")
    tienda_b = PuntoVenta(empresa_id=empresa.id, nombre="Tienda FAC B")
    tienda_nombre = PuntoVenta(empresa_id=empresa.id, nombre="Tienda FAC Nombre")
    s.add_all([tienda_a, tienda_b, tienda_nombre])
    s.flush()

    usuarios = {}

    def usuario(clave, rol, punto):
        u = Usuario(
            empresa_id=empresa.id,
            punto_id=punto.id if punto else None,
            username=f"fac_{clave}",
            email=f"fac_{clave}@test.gt",
            password_hash=hash_password("secreta123"),
            rol=rol,
        )
        s.add(u)
        usuarios[clave] = u

    usuario("tomador", UserRol.TOMADOR_ORDEN, tienda_a)
    usuario("resp", UserRol.RESP_TIENDA, tienda_a)
    usuario("gerente_punto", UserRol.GERENTE_PUNTO, tienda_a)
    usuario("gerente_general", UserRol.GERENTE_GENERAL, None)
    usuario("admin", UserRol.ADMIN, None)
    usuario("cocinero", UserRol.COCINERO, tienda_a)
    usuario("repartidor", UserRol.REPARTIDOR, tienda_a)
    usuario("bodeguero", UserRol.BODEGUERO, tienda_a)
    usuario("gerente_central", UserRol.GERENTE_CENTRAL, None)
    usuario("tomador_b", UserRol.TOMADOR_ORDEN, tienda_b)
    usuario("resp_b", UserRol.RESP_TIENDA, tienda_b)
    usuario("tomador_nombre", UserRol.TOMADOR_ORDEN, tienda_nombre)
    s.commit()

    out = {
        "a": tienda_a.id,
        "b": tienda_b.id,
        "nombre": tienda_nombre.id,
        "empresa_id": empresa.id,
    }
    for clave, u in usuarios.items():
        out[clave] = {
            "user_id": u.id,
            "username": u.username,
            "punto_id": u.punto_id,
            "rol": u.rol.value,
            "empresa_id": u.empresa_id,
        }
    s.close()
    return out


def _orden(S, punto_id, *, metodo=MetodoPago.EFECTIVO, estado_cobro="cobrada",
           estado=OrdenEstado.PENDIENTE, cliente_nombre="Cliente prueba") -> int:
    s = S()
    o = Orden(
        punto_id=punto_id,
        numero_orden=f"TEST-{uuid.uuid4().hex[:12]}",
        cliente_nombre=cliente_nombre,
        metodo_pago=metodo,
        total=100.0,
        estado=estado,
        estado_cobro=estado_cobro,
    )
    s.add(o)
    s.commit()
    oid = o.id
    s.close()
    return oid


def _put(api, usuario, orden_id, body=None):
    return api.put(
        f"/api/ordenes/{orden_id}/datos-factura",
        json=DATOS_OK if body is None else body,
        headers=_auth(usuario),
    )


def _marcar(api, usuario, orden_id):
    return api.post(
        f"/api/ordenes/{orden_id}/datos-factura/marcar-generada", headers=_auth(usuario)
    )


def _fila(S, orden_id):
    s = S()
    try:
        return s.execute(
            select(DatosFacturacion).where(DatosFacturacion.orden_id == orden_id)
        ).scalar_one_or_none()
    finally:
        s.close()


def _auditorias(S, orden_id, accion):
    s = S()
    try:
        return s.execute(
            select(AuditLog)
            .where(AuditLog.entidad == "orden", AuditLog.entidad_id == str(orden_id),
                   AuditLog.accion == accion)
            .order_by(AuditLog.id)
        ).scalars().all()
    finally:
        s.close()


ITEMS = [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 100}]


# ---------------------------------------------------------------------------
# Constantes de roles
# ---------------------------------------------------------------------------


def test_roles_captura_factura_son_vendedores_mas_cobradores():
    """_ROLES_CAPTURA_FACTURA no se importa de router_impresion (import
    circular): esta prueba evita que las dos listas se separen."""
    assert set(_ROLES_CAPTURA_FACTURA) == set(ROLES_IMPRESION_TICKET) | set(_ROLES_CONFIRMAR_COBRO)


# ---------------------------------------------------------------------------
# Nombre obligatorio al cobrar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["efectivo", "tarjeta", "transferencia"])
@pytest.mark.parametrize("nombre", [None, "", "   ", " a ", ".."], ids=["falta", "vacio", "espacios", "una-letra", "puntos"])
def test_orden_sin_nombre_util_da_422(api, ctx, metodo, nombre):
    body = {"metodo_pago": metodo, "items": ITEMS}
    if nombre is not None:
        body["cliente_nombre"] = nombre
    r = api.post("/api/ordenes/", json=body, headers=_auth(ctx["tomador"]))
    assert r.status_code == 422, r.text
    err = r.json()["detail"][0]
    assert err["loc"][-1] == "cliente_nombre"
    assert "nombre del cliente es obligatorio" in err["msg"]


def test_orden_guarda_el_nombre_sin_espacios_sobrantes(api, ctx):
    r = api.post(
        "/api/ordenes/",
        json={"cliente_nombre": "  Ana   López  ", "metodo_pago": "tarjeta", "items": ITEMS},
        headers=_auth(ctx["tomador_nombre"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cliente_nombre"] == "Ana López"
    # Una orden recién creada no tiene fila de datos fiscales.
    assert body["datos_factura"] is None


def test_orden_con_nombre_de_mas_de_100_caracteres_da_422(api, ctx):
    r = api.post(
        "/api/ordenes/",
        json={"cliente_nombre": "A" * 101, "metodo_pago": "tarjeta", "items": ITEMS},
        headers=_auth(ctx["tomador"]),
    )
    assert r.status_code == 422


def _transaccion(metodo, *, orden_id=None, cliente_nombre=None):
    body = {
        "orden_id": orden_id,
        "metodo_pago": metodo,
        "precio_venta": 50,
        "items": [{"nombre": "Prueba", "cantidad": 1, "unidad": "pieza",
                   "precio_unitario": 50, "subtotal": 50}],
    }
    if cliente_nombre is not None:
        body["cliente_nombre"] = cliente_nombre
    return body


@pytest.mark.parametrize("metodo", ["tarjeta", "transferencia"])
def test_transaccion_sin_orden_y_sin_nombre_da_422(api, ctx, metodo):
    r = api.post("/api/ordenes/transacciones/", json=_transaccion(metodo), headers=_auth(ctx["tomador"]))
    assert r.status_code == 422, r.text
    assert "nombre del cliente es obligatorio" in r.json()["detail"][0]["msg"]


@pytest.mark.parametrize("metodo", ["tarjeta", "transferencia"])
def test_transaccion_sin_orden_con_nombre_pasa(api, ctx, metodo):
    r = api.post(
        "/api/ordenes/transacciones/",
        json=_transaccion(metodo, cliente_nombre="Luis"),
        headers=_auth(ctx["tomador"]),
    )
    assert r.status_code == 200, r.text


def test_efectivo_sin_orden_y_sin_nombre_sigue_dando_400(api, ctx):
    """La regla "no existe efectivo sin orden" (400) va antes que el nombre."""
    r = api.post("/api/ordenes/transacciones/", json=_transaccion("efectivo"), headers=_auth(ctx["tomador"]))
    assert r.status_code == 400
    assert "orden" in r.json()["detail"].lower()


@pytest.mark.parametrize("metodo", ["efectivo", "tarjeta"])
def test_transaccion_con_orden_no_vuelve_a_exigir_nombre(api, ctx, S, metodo):
    orden_id = _orden(S, ctx["a"], metodo=MetodoPago(metodo))
    r = api.post(
        "/api/ordenes/transacciones/",
        json=_transaccion(metodo, orden_id=orden_id),
        headers=_auth(ctx["tomador"]),
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Formato del NIT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entrada,esperado", [
    ("12345678-9", "12345678-9"),
    ("1234567-K", "1234567-K"),
    ("1234567-k", "1234567-K"),
    ("1234567K", "1234567K"),
    ("12345678", "12345678"),
    ("  1234567-8  ", "1234567-8"),
    ("1" * 20, "1" * 20),
])
def test_nit_valido(entrada, esperado):
    assert normalizar_nit(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "123 456",
    "CF",  # TODO(facturación): pendiente decidir si "CF" es válido; hoy se rechaza.
    "1" * 21,
    "",
    "   ",
    "-1234567",
    "1234567-",
    "1234567-KK",
    "12-34-5",
    "1234567-X",
    "١٢٣٤٥",  # dígitos no ASCII
    "1234\n567",  # salto de línea en medio (en los extremos se recorta como un espacio)
])
def test_nit_invalido(entrada):
    with pytest.raises(Exception):
        normalizar_nit(entrada)


def test_put_con_nit_invalido_da_422_y_no_crea_fila(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx["tomador"], orden_id, {**DATOS_OK, "nit": "123 456"})
    assert r.status_code == 422
    assert "NIT inválido" in r.json()["detail"][0]["msg"]
    assert _fila(S, orden_id) is None


def test_put_guarda_nit_en_mayusculas(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx["tomador"], orden_id, {**DATOS_OK, "nit": "1234567-k"})
    assert r.status_code == 200, r.text
    assert r.json()["nit"] == "1234567-K"
    assert _fila(S, orden_id).nit == "1234567-K"


# ---------------------------------------------------------------------------
# PUT datos-factura: validación del body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["nit", "nombre_fiscal", "direccion_fiscal"])
def test_requiere_factura_exige_los_tres_campos(api, ctx, S, campo):
    orden_id = _orden(S, ctx["a"])
    body = {**DATOS_OK, campo: "  "}
    r = _put(api, ctx["tomador"], orden_id, body)
    assert r.status_code == 422, r.text
    assert _fila(S, orden_id) is None


def test_sin_factura_los_campos_se_ignoran_y_quedan_null(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx["tomador"], orden_id, {**DATOS_OK, "requiere_factura": False})
    assert r.status_code == 200, r.text
    f = _fila(S, orden_id)
    assert f.requiere_factura is False
    assert (f.nit, f.nombre_fiscal, f.direccion_fiscal) == (None, None, None)


def test_put_no_acepta_punto_id_en_el_body(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx["resp"], orden_id, {**DATOS_OK, "punto_id": ctx["b"]})
    assert r.status_code == 422
    assert _fila(S, orden_id) is None


def test_put_orden_inexistente_da_404(api, ctx):
    assert _put(api, ctx["resp"], 999999999).status_code == 404


# ---------------------------------------------------------------------------
# PUT datos-factura: matriz de roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["tomador", "resp", "gerente_punto", "gerente_general", "admin"])
def test_put_crea_la_fila_roles_permitidos(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx[rol], orden_id)
    assert r.status_code == 200, r.text
    f = _fila(S, orden_id)
    assert f.capturado_por == ctx[rol]["user_id"]
    assert f.capturado_at is not None
    assert f.actualizado_por is None


@pytest.mark.parametrize("rol", ["cocinero", "repartidor", "bodeguero", "gerente_central"])
def test_put_roles_sin_permiso_dan_403(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx[rol], orden_id).status_code == 403
    assert _fila(S, orden_id) is None


@pytest.mark.parametrize("rol", ["tomador_b", "resp_b"])
def test_put_de_otra_tienda_da_403(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    r = _put(api, ctx[rol], orden_id)
    assert r.status_code == 403
    assert _fila(S, orden_id) is None


@pytest.mark.parametrize("cambio", [
    {"nit": "7654321-0"},
    {"nombre_fiscal": "Otro Nombre"},
    {"direccion_fiscal": "Zona 1"},
    {"requiere_factura": False},
    {},  # mismos datos: igual queda bloqueado para el vendedor
], ids=["nit", "nombre_fiscal", "direccion_fiscal", "requiere_factura", "sin-cambios"])
def test_vendedor_no_edita_si_la_fila_ya_existe(api, ctx, S, cambio):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    r = _put(api, ctx["tomador"], orden_id, {**DATOS_OK, **cambio})
    assert r.status_code == 403, r.text
    f = _fila(S, orden_id)
    assert (f.requiere_factura, f.nit, f.nombre_fiscal, f.direccion_fiscal) == (
        True, "1234567-8", "Cliente Fiscal S.A.", "Ciudad"
    )


@pytest.mark.parametrize("rol", ["resp", "gerente_punto", "gerente_general", "admin"])
def test_cobrador_edita_mientras_no_este_generada(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    r = _put(api, ctx[rol], orden_id, {**DATOS_OK, "nit": "7654321-0"})
    assert r.status_code == 200, r.text
    f = _fila(S, orden_id)
    assert f.nit == "7654321-0"
    assert f.capturado_por == ctx["tomador"]["user_id"]
    assert f.actualizado_por == ctx[rol]["user_id"]
    assert f.actualizado_at is not None


def test_put_en_orden_cancelada_da_409(api, ctx, S):
    orden_id = _orden(S, ctx["a"], estado=OrdenEstado.CANCELADO)
    assert _put(api, ctx["resp"], orden_id).status_code == 409
    assert _fila(S, orden_id) is None


# ---------------------------------------------------------------------------
# Auditoría de PUT
# ---------------------------------------------------------------------------


def test_auditoria_de_captura_y_edicion_con_antes_despues_y_nit_enmascarado(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    assert _put(api, ctx["resp"], orden_id, {**DATOS_OK, "nit": "7654321-0",
                                              "nombre_fiscal": "Nuevo Nombre"}).status_code == 200

    logs = _auditorias(S, orden_id, "DATOS_FACTURA_ACTUALIZADOS")
    assert len(logs) == 2
    alta, edicion = logs

    assert alta.usuario_id == ctx["tomador"]["user_id"]
    assert alta.punto_id == ctx["a"]
    assert alta.detalle["antes"] == {
        "requiere_factura": None, "nit": None, "nombre_fiscal": None, "direccion_fiscal": None,
    }
    assert alta.detalle["despues"] == {
        "requiere_factura": True, "nit": "***7-8",
        "nombre_fiscal": "Cliente Fiscal S.A.", "direccion_fiscal": "Ciudad",
    }

    # Solo los campos que cambiaron, con el NIT enmascarado en ambos lados.
    assert edicion.usuario_id == ctx["resp"]["user_id"]
    assert edicion.detalle["antes"] == {"nit": "***7-8", "nombre_fiscal": "Cliente Fiscal S.A."}
    assert edicion.detalle["despues"] == {"nit": "***1-0", "nombre_fiscal": "Nuevo Nombre"}
    # El NIT completo no aparece en ninguna parte del log.
    for log in logs:
        assert "1234567-8" not in str(log.detalle)
        assert "7654321-0" not in str(log.detalle)


def test_guardar_sin_cambios_no_genera_auditoria(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert len(_auditorias(S, orden_id, "DATOS_FACTURA_ACTUALIZADOS")) == 1
    assert _fila(S, orden_id).actualizado_por is None


# ---------------------------------------------------------------------------
# Marcar factura generada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["resp", "gerente_punto", "gerente_general", "admin"])
def test_marcar_generada_roles_cobradores(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    r = _marcar(api, ctx[rol], orden_id)
    assert r.status_code == 200, r.text
    assert r.json()["factura_generada"] is True
    f = _fila(S, orden_id)
    assert f.factura_generada is True
    assert f.factura_generada_por == ctx[rol]["user_id"]
    assert f.factura_generada_at is not None


@pytest.mark.parametrize("rol", ["tomador", "cocinero", "repartidor", "bodeguero", "gerente_central"])
def test_marcar_generada_roles_sin_permiso_dan_403(api, ctx, S, rol):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert _marcar(api, ctx[rol], orden_id).status_code == 403
    assert _fila(S, orden_id).factura_generada is False


def test_marcar_generada_de_otra_tienda_da_403(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp_b"], orden_id).status_code == 403


def test_marcar_generada_en_orden_pendiente_de_cobro_da_409(api, ctx, S):
    orden_id = _orden(S, ctx["a"], estado_cobro="pendiente_recibir")
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    r = _marcar(api, ctx["resp"], orden_id)
    assert r.status_code == 409
    assert "cobrada" in r.json()["detail"]
    assert _fila(S, orden_id).factura_generada is False


def test_marcar_generada_en_orden_cancelada_da_409(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    s = S()
    s.get(Orden, orden_id).estado = OrdenEstado.CANCELADO
    s.commit()
    s.close()
    assert _marcar(api, ctx["resp"], orden_id).status_code == 409


def test_marcar_generada_dos_veces_da_409(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 409


def test_marcar_generada_sin_requerir_factura_da_422(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id, {"requiere_factura": False}).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 422


def test_marcar_generada_sin_fila_da_422(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _marcar(api, ctx["resp"], orden_id).status_code == 422


def test_marcar_generada_con_tarjeta_que_nace_cobrada(api, ctx, S):
    orden_id = _orden(S, ctx["a"], metodo=MetodoPago.TARJETA)
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 200


def test_marcar_generada_registra_auditoria_con_nit_enmascarado(api, ctx, S):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["resp"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 200
    logs = _auditorias(S, orden_id, "FACTURA_MARCADA_GENERADA")
    assert len(logs) == 1
    assert logs[0].usuario_id == ctx["resp"]["user_id"]
    assert logs[0].detalle["nit"] == "***7-8"


@pytest.mark.parametrize("rol", ["tomador", "resp", "admin"])
def test_editar_despues_de_marcar_generada_da_409(api, ctx, S, rol):
    """409 para cualquier rol, también para el vendedor (antes que su 403)."""
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    assert _marcar(api, ctx["resp"], orden_id).status_code == 200
    r = _put(api, ctx[rol], orden_id, {**DATOS_OK, "nit": "7654321-0"})
    assert r.status_code == 409
    assert "generada" in r.json()["detail"]
    assert _fila(S, orden_id).nit == "1234567-8"


# ---------------------------------------------------------------------------
# Lectura: datos_factura en las respuestas de órdenes
# ---------------------------------------------------------------------------


def test_listado_incluye_datos_factura_o_null_y_respeta_la_tienda(api, ctx, S):
    con_datos = _orden(S, ctx["a"])
    sin_datos = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], con_datos).status_code == 200

    r = api.get("/api/ordenes/", headers=_auth(ctx["resp"]))
    assert r.status_code == 200
    por_id = {o["id"]: o for o in r.json()}
    assert por_id[con_datos]["datos_factura"]["nit"] == "1234567-8"
    assert por_id[con_datos]["datos_factura"]["factura_generada"] is False
    assert por_id[sin_datos]["datos_factura"] is None
    assert {o["punto_id"] for o in r.json()} == {ctx["a"]}

    # Un vendedor de otra tienda no ve esas órdenes ni sus datos fiscales.
    r = api.get("/api/ordenes/", headers=_auth(ctx["tomador_b"]))
    assert r.status_code == 200
    ids_b = {o["id"] for o in r.json()}
    assert con_datos not in ids_b and sin_datos not in ids_b


def test_confirmar_cobro_devuelve_datos_factura(api, ctx, S):
    orden_id = _orden(S, ctx["a"], estado_cobro="pendiente_recibir")
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    r = api.post(
        f"/api/ordenes/{orden_id}/confirmar-cobro",
        json={"monto_recibido": 100, "vuelto_entregado": 0},
        headers=_auth(ctx["resp"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["datos_factura"]["requiere_factura"] is True


def test_payload_del_ticket_no_lleva_datos_fiscales(ctx, S, api):
    orden_id = _orden(S, ctx["a"])
    assert _put(api, ctx["tomador"], orden_id).status_code == 200
    s = S()
    try:
        orden = s.get(Orden, orden_id)
        payload = _payload_ticket(s, orden, s.get(PuntoVenta, ctx["a"]))
    finally:
        s.close()
    assert "datos_factura" not in payload["orden"]
    assert "1234567-8" not in str(payload)
    assert payload["orden"]["cliente_nombre"] == "Cliente prueba"
