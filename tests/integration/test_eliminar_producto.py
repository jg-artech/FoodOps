"""DELETE /api/config/productos/{id}: quitar un producto del menú.

- No borra la fila: la deja con activo = false (las órdenes guardan nombre y
  precio en sus items; las que están en curso siguen usando la receta).
- Solo gerencia (gerente_general, admin), como el resto de /api/config/productos.
- El producto eliminado desaparece de /api/config/productos y de
  /api/productos-menu, no se puede editar (404) y su nombre queda libre.
- Queda auditoría ELIMINAR_PRODUCTO.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import AuditLog, Empresa, PuntoVenta, Usuario, UserRol
from foodops.db.models_stock import ProductoMenu

_HASH = hash_password("Clave-eliminar-1")
URL = "/api/config/productos"


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def usuarios(S):
    s = S()
    e = Empresa(nombre="Eliminar Test", nit=f"TEST-EP-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda EP {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"ep_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@test.gt", password_hash=_HASH, rol=rol,
        )
        s.add(u)
        s.flush()
        return {"user_id": u.id, "username": u.username, "punto_id": u.punto_id,
                "rol": u.rol.value, "empresa_id": u.empresa_id}

    out = {
        "admin": usuario(UserRol.ADMIN, None),
        "gerente_general": usuario(UserRol.GERENTE_GENERAL, None),
        "resp_tienda": usuario(UserRol.RESP_TIENDA, p.id),
        "gerente_punto": usuario(UserRol.GERENTE_PUNTO, p.id),
        "vendedor": usuario(UserRol.TOMADOR_ORDEN, p.id),
    }
    s.commit()
    s.close()
    return out


def _body(nombre=None):
    return {"nombre": nombre or f"Producto EP {uuid.uuid4().hex[:8]}", "precio": 30,
            "categoria": "guarniciones", "unidad": "porción", "componentes": []}


def _crear(api, usuarios, nombre=None):
    r = api.post(URL, json=_body(nombre), headers=_auth(usuarios["admin"]))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("rol", ["admin", "gerente_general"])
def test_gerencia_elimina_y_la_fila_queda_inactiva(api, usuarios, S, rol):
    p = _crear(api, usuarios)
    r = api.delete(f"{URL}/{p['id']}", headers=_auth(usuarios[rol]))
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False
    s = S()
    fila = s.get(ProductoMenu, p["id"])
    assert fila is not None and fila.activo is False
    s.close()


@pytest.mark.parametrize("rol", ["resp_tienda", "gerente_punto", "vendedor"])
def test_otros_roles_no_eliminan(api, usuarios, S, rol):
    p = _crear(api, usuarios)
    assert api.delete(f"{URL}/{p['id']}", headers=_auth(usuarios[rol])).status_code == 403
    s = S()
    assert s.get(ProductoMenu, p["id"]).activo is True
    s.close()


def test_eliminado_desaparece_del_menu_y_de_configuracion(api, usuarios):
    p = _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    assert api.delete(f"{URL}/{p['id']}", headers=h).status_code == 200
    assert p["id"] not in {x["id"] for x in api.get(URL, headers=h).json()}
    menu = api.get("/api/productos-menu", headers=_auth(usuarios["vendedor"])).json()
    assert p["id"] not in {x["id"] for x in menu}


def test_eliminar_dos_veces_o_inexistente_da_404(api, usuarios):
    p = _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    assert api.delete(f"{URL}/{p['id']}", headers=h).status_code == 200
    assert api.delete(f"{URL}/{p['id']}", headers=h).status_code == 404
    assert api.delete(f"{URL}/999999999", headers=h).status_code == 404


def test_no_se_edita_un_eliminado(api, usuarios):
    p = _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    assert api.delete(f"{URL}/{p['id']}", headers=h).status_code == 200
    assert api.patch(f"{URL}/{p['id']}", json=_body(), headers=h).status_code == 404


def test_el_nombre_queda_libre_tras_eliminar(api, usuarios):
    nombre = f"Reusable {uuid.uuid4().hex[:8]}"
    p = _crear(api, usuarios, nombre)
    h = _auth(usuarios["admin"])
    assert api.post(URL, json=_body(nombre), headers=h).status_code == 400
    assert api.delete(f"{URL}/{p['id']}", headers=h).status_code == 200
    nuevo = api.post(URL, json=_body(nombre), headers=h)
    assert nuevo.status_code == 201
    assert nuevo.json()["id"] != p["id"]


def test_auditoria(api, usuarios, S):
    p = _crear(api, usuarios)
    assert api.delete(f"{URL}/{p['id']}", headers=_auth(usuarios["gerente_general"])).status_code == 200
    s = S()
    fila = s.execute(select(AuditLog).where(
        AuditLog.accion == "ELIMINAR_PRODUCTO", AuditLog.entidad_id == str(p["id"]),
    )).scalars().one()
    s.close()
    assert fila.usuario_id == usuarios["gerente_general"]["user_id"]
    assert fila.detalle["nombre"] == p["nombre"]
