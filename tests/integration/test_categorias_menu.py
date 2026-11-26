"""Categorías del menú en la base (migración 017).

- GET /api/config/categorias: cualquier rol autenticado, en orden de posición;
  las inactivas solo para gerencia con incluir_inactivas.
- POST, PATCH y PUT /orden: solo gerente_general y admin.
- La clave sale del nombre y no cambia. Sin DELETE: se desactiva, pero no si
  tiene productos activos (409).
- PUT /orden exige todas las categorías, una vez cada una.
"""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import AuditLog, Empresa, PuntoVenta, Usuario, UserRol
from foodops.db.models_stock import CategoriaMenu, ProductoMenu

_HASH = hash_password("Clave-categorias-1")
URL = "/api/config/categorias"


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def usuarios(S):
    s = S()
    e = Empresa(nombre="Categorias Test", nit=f"TEST-CM-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda CM {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"cm_{uuid.uuid4().hex[:10]}",
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
        "vendedor": usuario(UserRol.TOMADOR_ORDEN, p.id),
    }
    s.commit()
    s.close()
    return out


@pytest.fixture
def limpio(S):
    """La tabla de pruebas se crea vacía (create_all): cada prueba parte de cero."""
    s = S()
    s.execute(delete(CategoriaMenu))
    s.commit()
    s.close()
    yield
    s = S()
    s.execute(delete(CategoriaMenu))
    s.commit()
    s.close()


def _crear(api, usuarios, nombre, emoji=None, rol="admin"):
    r = api.post(URL, json={"nombre": nombre, "emoji": emoji}, headers=_auth(usuarios[rol]))
    assert r.status_code == 201, r.text
    return r.json()


def test_crear_deriva_la_clave_y_va_al_final(api, usuarios, limpio):
    a = _crear(api, usuarios, "Combos")
    b = _crear(api, usuarios, "  Pollo   por piezas ", "🍗")
    assert a["clave"] == "combos" and a["posicion"] == 1
    assert b["clave"] == "pollo_por_piezas" and b["nombre"] == "Pollo por piezas" and b["posicion"] == 2
    assert b["emoji"] == "🍗" and b["activo"] is True
    c = _crear(api, usuarios, "Bebidas Frías y Calientes")
    assert c["clave"] == "bebidas_frias_y_calientes"


def test_nombre_o_clave_repetidos_dan_400(api, usuarios, limpio):
    _crear(api, usuarios, "Bebidas")
    h = _auth(usuarios["admin"])
    assert api.post(URL, json={"nombre": "BEBIDAS"}, headers=h).status_code == 400
    assert api.post(URL, json={"nombre": "bébidas"}, headers=h).status_code == 400


def test_nombre_sin_letras_da_422(api, usuarios, limpio):
    h = _auth(usuarios["admin"])
    assert api.post(URL, json={"nombre": "   "}, headers=h).status_code == 422
    assert api.post(URL, json={"nombre": "!!!"}, headers=h).status_code == 422


@pytest.mark.parametrize("rol", ["resp_tienda", "vendedor"])
def test_solo_gerencia_administra(api, usuarios, limpio, rol):
    cat = _crear(api, usuarios, "Combos")
    h = _auth(usuarios[rol])
    assert api.post(URL, json={"nombre": "Otra"}, headers=h).status_code == 403
    assert api.patch(f"{URL}/{cat['id']}", json={"nombre": "X"}, headers=h).status_code == 403
    assert api.put(f"{URL}/orden", json={"ids": [cat["id"]]}, headers=h).status_code == 403


def test_cualquier_rol_lee_las_activas_en_orden(api, usuarios, limpio):
    a = _crear(api, usuarios, "Combos")
    b = _crear(api, usuarios, "Costillas")
    c = _crear(api, usuarios, "Viejas")
    h = _auth(usuarios["admin"])
    assert api.patch(f"{URL}/{c['id']}", json={"activo": False}, headers=h).status_code == 200
    vendedor = api.get(URL, params={"incluir_inactivas": True}, headers=_auth(usuarios["vendedor"])).json()
    assert [x["id"] for x in vendedor] == [a["id"], b["id"]]
    gerencia = api.get(URL, params={"incluir_inactivas": True}, headers=h).json()
    assert [x["id"] for x in gerencia] == [a["id"], b["id"], c["id"]]


def test_reordenar(api, usuarios, limpio, S):
    a, b, c = (_crear(api, usuarios, n) for n in ("Pollos", "Costillas", "Combos"))
    h = _auth(usuarios["gerente_general"])
    r = api.put(f"{URL}/orden", json={"ids": [c["id"], b["id"], a["id"]]}, headers=h)
    assert r.status_code == 200
    lista = api.get(URL, headers=h).json()
    assert [x["clave"] for x in lista] == ["combos", "costillas", "pollos"]
    assert [x["posicion"] for x in lista] == [1, 2, 3]
    s = S()
    fila = s.execute(select(AuditLog).where(AuditLog.accion == "CATEGORIAS_MENU_ORDENADAS")
                     .order_by(AuditLog.id.desc())).scalars().first()
    s.close()
    assert fila.detalle == {"antes": ["pollos", "costillas", "combos"], "despues": ["combos", "costillas", "pollos"]}


def test_reordenar_exige_todas_una_vez(api, usuarios, limpio):
    a, b = _crear(api, usuarios, "Pollos"), _crear(api, usuarios, "Combos")
    h = _auth(usuarios["admin"])
    assert api.put(f"{URL}/orden", json={"ids": [a["id"]]}, headers=h).status_code == 400
    assert api.put(f"{URL}/orden", json={"ids": [a["id"], a["id"]]}, headers=h).status_code == 400
    assert api.put(f"{URL}/orden", json={"ids": [a["id"], b["id"], 999999]}, headers=h).status_code == 400


def test_renombrar_no_cambia_la_clave_y_audita(api, usuarios, limpio, S):
    cat = _crear(api, usuarios, "Bebidas")
    r = api.patch(f"{URL}/{cat['id']}", json={"nombre": "Refrescos", "emoji": "🥤"}, headers=_auth(usuarios["admin"]))
    assert r.status_code == 200
    assert r.json()["clave"] == "bebidas" and r.json()["nombre"] == "Refrescos" and r.json()["emoji"] == "🥤"
    s = S()
    fila = s.execute(select(AuditLog).where(
        AuditLog.accion == "CATEGORIA_MENU_ACTUALIZADA", AuditLog.entidad_id == str(cat["id"]),
    )).scalars().one()
    s.close()
    assert fila.detalle["antes"]["nombre"] == "Bebidas" and fila.detalle["despues"]["nombre"] == "Refrescos"


def test_no_se_desactiva_con_productos_activos(api, usuarios, limpio, S):
    cat = _crear(api, usuarios, f"Temporal {uuid.uuid4().hex[:6]}")
    s = S()
    prod = ProductoMenu(nombre=f"Prod {uuid.uuid4().hex[:8]}", precio=10, categoria=cat["clave"], activo=True)
    s.add(prod)
    s.commit()
    pid = prod.id
    s.close()
    h = _auth(usuarios["admin"])
    r = api.patch(f"{URL}/{cat['id']}", json={"activo": False}, headers=h)
    assert r.status_code == 409
    assert "1 producto" in r.json()["detail"]
    assert api.delete(f"/api/config/productos/{pid}", headers=h).status_code == 200
    assert api.patch(f"{URL}/{cat['id']}", json={"activo": False}, headers=h).json()["activo"] is False
    assert api.patch(f"{URL}/{cat['id']}", json={"activo": True}, headers=h).json()["activo"] is True


def test_no_hay_delete(api, usuarios, limpio):
    cat = _crear(api, usuarios, "Combos")
    assert api.delete(f"{URL}/{cat['id']}", headers=_auth(usuarios["admin"])).status_code == 405


def test_inexistente_da_404(api, usuarios, limpio):
    assert api.patch(f"{URL}/999999", json={"nombre": "X"}, headers=_auth(usuarios["admin"])).status_code == 404
