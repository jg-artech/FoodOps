"""contenido como campo único del producto (migración 015).

- POST y PATCH /api/config/productos aceptan contenido (opcional, máx. 500).
- descripcion ya no existe: si llega en el body se ignora sin error, y no
  aparece en ninguna respuesta.
- GET /api/config/productos y GET /api/productos-menu devuelven contenido.
- Permisos sin cambios: config solo gerencia; productos-menu cualquier rol.
"""

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import Empresa, PuntoVenta, Usuario, UserRol
from foodops.db.models_stock import ProductoMenu

_HASH = hash_password("Clave-contenido-1")


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def usuarios(S):
    s = S()
    e = Empresa(nombre="Contenido Test", nit=f"TEST-CT-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda CT {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"ct_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=rol,
        )
        s.add(u)
        s.flush()
        return {"user_id": u.id, "username": u.username, "punto_id": u.punto_id,
                "rol": u.rol.value, "empresa_id": u.empresa_id}

    out = {
        "admin": usuario(UserRol.ADMIN, None),
        "vendedor": usuario(UserRol.TOMADOR_ORDEN, p.id),
    }
    s.commit()
    s.close()
    return out


def _body(**extra):
    body = {
        "nombre": f"Combo prueba {uuid.uuid4().hex[:8]}",
        "precio": 99,
        "categoria": "combos",
        "unidad": "combo",
        "componentes": [],
    }
    body.update(extra)
    return body


def _crear(api, usuarios, **extra):
    r = api.post("/api/config/productos", json=_body(**extra), headers=_auth(usuarios["admin"]))
    assert r.status_code == 201, r.text
    return r.json()


def test_crear_con_contenido(api, usuarios, S):
    p = _crear(api, usuarios, contenido="  1 pollo, 3 guarniciones  ")
    assert p["contenido"] == "1 pollo, 3 guarniciones"
    assert "descripcion" not in p
    s = S()
    assert s.get(ProductoMenu, p["id"]).contenido == "1 pollo, 3 guarniciones"
    s.close()


def test_crear_sin_contenido_queda_nulo(api, usuarios):
    assert _crear(api, usuarios)["contenido"] is None
    assert _crear(api, usuarios, contenido="   ")["contenido"] is None


def test_descripcion_en_el_body_se_ignora_sin_error(api, usuarios):
    p = _crear(api, usuarios, descripcion="texto viejo", contenido="texto nuevo")
    assert p["contenido"] == "texto nuevo"
    assert "descripcion" not in p
    p = _crear(api, usuarios, descripcion="solo descripcion")
    assert p["contenido"] is None


def test_editar_contenido(api, usuarios):
    p = _crear(api, usuarios, contenido="antes")
    body = _body(nombre=p["nombre"], contenido="después", descripcion="ignorada")
    r = api.patch(f"/api/config/productos/{p['id']}", json=body, headers=_auth(usuarios["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["contenido"] == "después"
    assert "descripcion" not in r.json()


def test_patch_sin_contenido_no_lo_borra_y_vacio_lo_limpia(api, usuarios):
    p = _crear(api, usuarios, contenido="se conserva")
    url = f"/api/config/productos/{p['id']}"
    r = api.patch(url, json=_body(nombre=p["nombre"]), headers=_auth(usuarios["admin"]))
    assert r.json()["contenido"] == "se conserva"
    r = api.patch(url, json=_body(nombre=p["nombre"], contenido=""), headers=_auth(usuarios["admin"]))
    assert r.json()["contenido"] is None


def test_contenido_maximo_500(api, usuarios):
    assert _crear(api, usuarios, contenido="x" * 500)["contenido"] == "x" * 500
    r = api.post("/api/config/productos", json=_body(contenido="x" * 501),
                 headers=_auth(usuarios["admin"]))
    assert r.status_code == 422


def test_listado_config_devuelve_contenido(api, usuarios):
    p = _crear(api, usuarios, contenido="en el listado")
    lista = api.get("/api/config/productos", headers=_auth(usuarios["admin"])).json()
    fila = next(x for x in lista if x["id"] == p["id"])
    assert fila["contenido"] == "en el listado"
    assert all("descripcion" not in x for x in lista)


def test_productos_menu_devuelve_contenido_y_datos_del_pos(api, usuarios):
    p = _crear(api, usuarios, contenido="para el POS")
    r = api.get("/api/productos-menu", headers=_auth(usuarios["vendedor"]))
    assert r.status_code == 200
    fila = next(x for x in r.json() if x["id"] == p["id"])
    assert fila["contenido"] == "para el POS"
    assert fila["precio"] == 99
    assert fila["categoria"] == "combos"
    assert fila["unidad"] == "combo"
    assert all("descripcion" not in x for x in r.json())


def test_vendedor_no_edita_productos(api, usuarios):
    h = _auth(usuarios["vendedor"])
    assert api.post("/api/config/productos", json=_body(contenido="x"), headers=h).status_code == 403
    assert api.get("/api/config/productos", headers=h).status_code == 403
    p = _crear(api, usuarios, contenido="intacto")
    r = api.patch(f"/api/config/productos/{p['id']}",
                  json=_body(nombre=p["nombre"], contenido="cambiado"), headers=h)
    assert r.status_code == 403
