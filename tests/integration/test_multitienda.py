"""Aislamiento entre tiendas.

Cada caso reproduce un cruce que el backend permitía antes del soporte
multitienda (ver docs/AUDITORIA_MULTITIENDA.md). Los usuarios viven solo en
la BD de prueba; la de desarrollo no se toca.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import Empresa, Orden, PuntoVenta, Usuario, UserRol
from foodops.db.models_caja import CajaDiaria, FondoRepartidor, Gasto, ItemInventario
from foodops.db.models_stock import PedidoReabastecimiento, PedidoReabastecimientoItem


def _auth(usuario: dict) -> dict:
    """Cabecera Bearer para un usuario sembrado (dict plano: los objetos ORM
    quedan desligados al cerrar la sesión de la fixture)."""
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


@pytest.fixture(scope="module")
def datos(engine):
    """Dos empresas, tres tiendas y un usuario por rol relevante."""
    Session = sessionmaker(bind=engine)
    s = Session()

    empresa = Empresa(nombre="Asados a la Leña", nit="TEST-1")
    otra_empresa = Empresa(nombre="Competencia", nit="TEST-2")
    s.add_all([empresa, otra_empresa])
    s.flush()

    centro = PuntoVenta(empresa_id=empresa.id, nombre="Local Centro")
    jordan = PuntoVenta(empresa_id=empresa.id, nombre="Local Jordán")
    auxiliar = PuntoVenta(empresa_id=empresa.id, nombre="Local Auxiliar")
    ajena = PuntoVenta(empresa_id=otra_empresa.id, nombre="Tienda de otra empresa")
    s.add_all([centro, jordan, auxiliar, ajena])
    s.flush()

    creados = {}

    def usuario(username, rol, punto):
        u = Usuario(
            empresa_id=empresa.id,
            punto_id=punto.id if punto else None,
            username=username,
            email=f"{username}@test.gt",
            password_hash=hash_password("secreta123"),
            rol=rol,
        )
        s.add(u)
        creados[username] = u
        return u

    vendedor_centro = usuario("vendedor_centro", UserRol.TOMADOR_ORDEN, centro)
    resp_centro = usuario("resp_centro", UserRol.RESP_TIENDA, centro)
    resp_jordan = usuario("resp_jordan", UserRol.RESP_TIENDA, jordan)
    gerente_general = usuario("gg_test", UserRol.GERENTE_GENERAL, None)
    # Mismo patrón que el central_test real: gerente_central con una tienda
    # "de casa" (Centro), pero su ámbito debe ser abastecimiento, nunca el
    # detalle de órdenes de otra tienda.
    gerente_central = usuario("gc_test", UserRol.GERENTE_CENTRAL, centro)
    s.flush()

    # Una orden por tienda
    def orden(punto, numero, usuario_):
        o = Orden(
            punto_id=punto.id,
            numero_orden=numero,
            estado="PENDIENTE",
            metodo_pago="EFECTIVO",
            total=50.0,
            tomada_por=usuario_.id,
        )
        s.add(o)
        return o

    orden_centro = orden(centro, "ORD-CENTRO-1", vendedor_centro)
    orden_jordan = orden(jordan, "ORD-JORDAN-1", resp_jordan)

    item = ItemInventario(nombre="Pollo Entero", tipo="vendible", unidad="unidad", orden_conteo=1)
    s.add(item)
    s.flush()

    # Pedido de reabastecimiento confirmado en Jordán
    pedido_jordan = PedidoReabastecimiento(
        punto_id=jordan.id, tipo="normal", estado="confirmado", creado_por=resp_jordan.id
    )
    s.add(pedido_jordan)
    s.flush()
    s.add(
        PedidoReabastecimientoItem(
            pedido_id=pedido_jordan.id, item_inventario_id=item.id, cantidad_solicitada=10
        )
    )

    # Caja y fondo de repartidor en Jordán
    caja_jordan = CajaDiaria(
        punto_id=jordan.id,
        fecha=date.today(),
        fondo_inicial=100,
        estado="abierta",
        abierta_por=resp_jordan.id,
    )
    s.add(caja_jordan)
    s.flush()
    fondo_jordan = FondoRepartidor(
        caja_id=caja_jordan.id, repartidor_id=resp_jordan.id, monto_entregado=50
    )
    s.add(fondo_jordan)

    # Gasto en Jordán: para probar que el modo "todas las tiendas" de
    # gerencia (permitir_todas=True) realmente agrega entre tiendas y no
    # solo la propia.
    gasto_jordan = Gasto(
        caja_id=caja_jordan.id,
        punto_id=jordan.id,
        categoria="otros",
        descripcion="Gasto de prueba en Jordán",
        monto=15,
        registrado_por=resp_jordan.id,
    )
    s.add(gasto_jordan)

    s.commit()

    def credenciales(u: Usuario) -> dict:
        return {
            "user_id": u.id,
            "username": u.username,
            "punto_id": u.punto_id,
            "rol": u.rol.value,
            "empresa_id": u.empresa_id,
        }

    datos = {
        "centro": centro.id,
        "jordan": jordan.id,
        "auxiliar": auxiliar.id,
        "ajena": ajena.id,
        "vendedor_centro": credenciales(vendedor_centro),
        "resp_centro": credenciales(resp_centro),
        "resp_jordan": credenciales(resp_jordan),
        "gerente_general": credenciales(gerente_general),
        "gerente_central": credenciales(gerente_central),
        "orden_centro": orden_centro.id,
        "orden_jordan": orden_jordan.id,
        "pedido_jordan": pedido_jordan.id,
        "fondo_jordan": fondo_jordan.id,
        "item": item.id,
    }
    s.close()
    yield datos


# ---------------------------------------------------------------------------
# Lectura: un usuario de tienda solo ve su tienda
# ---------------------------------------------------------------------------


def test_vendedor_de_centro_solo_ve_ordenes_de_centro(api, datos):
    r = api.get("/api/ordenes/", headers=_auth(datos["vendedor_centro"]))
    assert r.status_code == 200
    numeros = {o["numero_orden"] for o in r.json()}
    assert numeros == {"ORD-CENTRO-1"}


def test_vendedor_de_centro_no_puede_pedir_las_ordenes_de_jordan(api, datos):
    r = api.get(
        "/api/ordenes/", params={"punto_id": datos["jordan"]}, headers=_auth(datos["vendedor_centro"])
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Escritura: los IDOR cross-tienda que cerró el paso 2
# ---------------------------------------------------------------------------


def test_vendedor_de_centro_no_puede_cancelar_una_orden_de_jordan(api, datos):
    r = api.put(
        f"/api/ordenes/{datos['orden_jordan']}/status",
        json={"estado": "cancelado"},
        headers=_auth(datos["vendedor_centro"]),
    )
    assert r.status_code == 403


def test_responsable_de_centro_no_puede_recibir_un_pedido_de_jordan(api, datos):
    r = api.post(
        f"/api/pedidos-reabastecimiento/{datos['pedido_jordan']}/recibir",
        json={"items_recibidos": [{"item_id": datos["item"], "cantidad": 10}]},
        headers=_auth(datos["resp_centro"]),
    )
    assert r.status_code == 403


def test_responsable_de_centro_no_puede_liquidar_un_fondo_de_jordan(api, datos):
    r = api.post(
        f"/api/fondos-repartidor/{datos['fondo_jordan']}/liquidar",
        json={"monto_liquidado": 50},
        headers=_auth(datos["resp_centro"]),
    )
    assert r.status_code == 403


def test_la_orden_toma_la_tienda_del_token_y_no_la_del_body(api, datos):
    r = api.post(
        "/api/ordenes/",
        json={
            "metodo_pago": "efectivo",
            "punto_id": datos["jordan"],  # intento de inyectar otra tienda
            "items": [{"producto": "1/4 Pollo", "cantidad": 1, "precio_unitario": 25}],
        },
        headers=_auth(datos["vendedor_centro"]),
    )
    assert r.status_code == 200
    # El número de orden lleva la tienda: confirma que se usó la del token.
    assert r.json()["numero_orden"].startswith(f"ORD-{datos['centro']}-")


# ---------------------------------------------------------------------------
# GERENTE_GENERAL
# ---------------------------------------------------------------------------


def test_gerente_central_no_puede_leer_ordenes_de_otra_tienda(api, datos):
    """gerente_central ve todas las tiendas para abastecimiento, pero su
    ámbito no incluye el detalle de órdenes de otra tienda (así se acordó:
    "gerente_central queda solo con abastecimiento"). Antes de este caso,
    resolver_punto_id trataba a cualquier rol de ROLES_MULTI_TIENDA como
    "ve todas" también aquí, y colaba el cruce."""
    r = api.get(
        "/api/ordenes/", params={"punto_id": datos["jordan"]}, headers=_auth(datos["gerente_central"])
    )
    assert r.status_code == 403


def test_gerente_general_ve_las_ordenes_de_cualquier_tienda(api, datos):
    gg = datos["gerente_general"]
    r = api.get("/api/ordenes/", params={"punto_id": datos["jordan"]}, headers=_auth(gg))
    assert r.status_code == 200
    assert {o["numero_orden"] for o in r.json()} == {"ORD-JORDAN-1"}


def test_gerente_general_sin_punto_id_ve_las_ordenes_de_todas_las_tiendas(api, datos):
    """Bug reportado 2026-10-18: GET /api/ordenes/ sin ?punto_id= caía en
    silencio a la tienda propia del usuario en vez de "todas". En el
    frontend esto se veía como: elegir en el selector una tienda sin
    órdenes y volver a "Todas las tiendas" no mostraba las demás órdenes
    (porque "todas" nunca existió para este endpoint, solo la tienda de
    casa del usuario)."""
    gg = datos["gerente_general"]
    r = api.get("/api/ordenes/", headers=_auth(gg))
    assert r.status_code == 200
    # Subset, no igualdad exacta: otros tests del mismo módulo crean órdenes
    # adicionales en Centro sobre este fixture compartido (scope="module").
    numeros = {o["numero_orden"] for o in r.json()}
    assert {"ORD-CENTRO-1", "ORD-JORDAN-1"} <= numeros
    assert all(o["punto_id"] in (datos["centro"], datos["jordan"]) for o in r.json())


def test_gerente_general_sin_punto_id_recibe_todas_las_tiendas(api, datos):
    r = api.get("/api/auth/usuarios", headers=_auth(datos["gerente_general"]))
    assert r.status_code == 200
    puntos = {u["punto_id"] for u in r.json()}
    assert {datos["centro"], datos["jordan"]} <= puntos


def test_gerente_general_no_puede_leer_una_tienda_de_otra_empresa(api, datos):
    r = api.get(
        "/api/ordenes/", params={"punto_id": datos["ajena"]}, headers=_auth(datos["gerente_general"])
    )
    assert r.status_code == 403


def test_gerente_general_recibe_404_si_la_tienda_no_existe(api, datos):
    r = api.get("/api/ordenes/", params={"punto_id": 999999}, headers=_auth(datos["gerente_general"]))
    assert r.status_code == 404


def test_gerente_general_ve_gastos_de_todas_las_tiendas_sin_punto_id(api, datos):
    """Modo "todas las tiendas" (permitir_todas=True) de /api/gastos: sin
    punto_id debe agregar entre tiendas, con punto_nombre por fila."""
    r = api.get("/api/gastos", headers=_auth(datos["gerente_general"]))
    assert r.status_code == 200
    por_tienda = {g["punto_id"]: g["punto_nombre"] for g in r.json()}
    assert por_tienda.get(datos["jordan"]) == "Local Jordán"


def test_responsable_de_jordan_no_ve_gastos_de_otras_tiendas(api, datos):
    r = api.get("/api/gastos", headers=_auth(datos["resp_jordan"]))
    assert r.status_code == 200
    assert {g["punto_id"] for g in r.json()} == {datos["jordan"]}


# ---------------------------------------------------------------------------
# Usuario sin tienda
# ---------------------------------------------------------------------------


def test_login_rechaza_un_rol_de_tienda_sin_tienda_asignada(api, datos, engine):
    """Caso heredado: usuarios creados antes del CHECK de la migración 010.

    El constraint impide crear ese usuario, así que se desactiva un momento
    para reproducir exactamente la fila que el 403 del login protege.
    """
    Session = sessionmaker(bind=engine)
    s = Session()
    s.execute(text("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_tienda_segun_rol"))
    huerfano = Usuario(
        empresa_id=1,
        punto_id=None,
        username="vendedor_sin_tienda",
        email="sin_tienda@test.gt",
        password_hash=hash_password("secreta123"),
        rol=UserRol.TOMADOR_ORDEN,
    )
    s.add(huerfano)
    s.commit()
    try:
        r = api.post(
            "/api/auth/login",
            json={"username": "vendedor_sin_tienda", "password": "secreta123"},
        )
        assert r.status_code == 403
        assert "tienda" in r.json()["detail"].lower()
    finally:
        s.delete(huerfano)
        s.commit()
        s.execute(
            text(
                "ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_tienda_segun_rol "
                "CHECK (punto_id IS NOT NULL OR rol::text IN "
                "('ADMIN', 'GERENTE_GENERAL', 'GERENTE_CENTRAL'))"
            )
        )
        s.commit()
        s.close()


def test_la_base_de_datos_rechaza_un_rol_de_tienda_sin_tienda(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(
        Usuario(
            empresa_id=1,
            punto_id=None,
            username="otro_sin_tienda",
            email="otro_sin_tienda@test.gt",
            password_hash="x",
            rol=UserRol.COCINERO,
        )
    )
    with pytest.raises(Exception):
        s.commit()
    s.rollback()
    s.close()
