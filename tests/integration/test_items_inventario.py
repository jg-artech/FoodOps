"""Mantenimiento de items de inventario (pestaña Inventario de Configuración).

- POST, PUT y PUT /orden: solo gerente_general y admin.
- Nombre único sin importar mayúsculas (activos e inactivos); espacios
  recortados. Sin orden_conteo, el item queda al final.
- GET con incluir_inactivos: solo gerencia ve los inactivos.
- No se desactiva un item que esté en la receta de un producto activo (409).
- PUT /orden exige todos los items, una vez cada uno, y renumera 1..N.
- Auditoría en crear, actualizar y ordenar.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import AuditLog, Empresa, PuntoVenta, Usuario, UserRol
from foodops.db.models_caja import ItemInventario
from foodops.db.models_stock import ProductoComponente, ProductoMenu

_HASH = hash_password("Clave-items-1")
URL = "/api/inventario/items"


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token(data=u)}"}


@pytest.fixture(scope="module")
def S(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(scope="module")
def usuarios(S):
    s = S()
    e = Empresa(nombre="Items Test", nit=f"TEST-II-{uuid.uuid4().hex[:6]}")
    s.add(e)
    s.flush()
    p = PuntoVenta(empresa_id=e.id, nombre=f"Tienda II {uuid.uuid4().hex[:6]}")
    s.add(p)
    s.flush()

    def usuario(rol, punto_id):
        u = Usuario(
            empresa_id=e.id, punto_id=punto_id, username=f"ii_{uuid.uuid4().hex[:10]}",
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
        "gerente_central": usuario(UserRol.GERENTE_CENTRAL, None),
        "vendedor": usuario(UserRol.TOMADOR_ORDEN, p.id),
    }
    s.commit()
    s.close()
    return out


def _nombre():
    return f"Item {uuid.uuid4().hex[:8]}"


def _crear(api, usuarios, rol="admin", **extra):
    body = {"nombre": _nombre(), "tipo": "vendible", "unidad": "unidad", **extra}
    r = api.post(URL, json=body, headers=_auth(usuarios[rol]))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("rol", ["admin", "gerente_general"])
def test_gerencia_crea_al_final_y_sin_tienda(api, usuarios, S, rol):
    s = S()
    maximo = s.execute(select(ItemInventario.orden_conteo).order_by(ItemInventario.orden_conteo.desc())).scalars().first() or 0
    s.close()
    item = _crear(api, usuarios, rol, nombre="  Mirinda   1.75L  " + uuid.uuid4().hex[:4])
    assert item["nombre"].startswith("Mirinda 1.75L ")
    assert item["orden_conteo"] == maximo + 1
    assert item["punto_id"] is None and item["activo"] is True


@pytest.mark.parametrize("rol", ["resp_tienda", "gerente_central", "vendedor"])
def test_otros_roles_no_administran(api, usuarios, rol):
    item = _crear(api, usuarios)
    h = _auth(usuarios[rol])
    assert api.post(URL, json={"nombre": _nombre(), "tipo": "insumo", "unidad": "lb"}, headers=h).status_code == 403
    assert api.put(f"{URL}/{item['id']}", json={"nombre": "X"}, headers=h).status_code == 403
    assert api.put(f"{URL}/orden", json={"ids": [item["id"]]}, headers=h).status_code == 403


def test_nombre_repetido_da_400_tambien_al_editar(api, usuarios):
    a, b = _crear(api, usuarios), _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    assert api.post(URL, json={"nombre": a["nombre"].upper(), "tipo": "insumo", "unidad": "lb"}, headers=h).status_code == 400
    assert api.put(f"{URL}/{b['id']}", json={"nombre": a["nombre"].lower()}, headers=h).status_code == 400
    assert api.put(f"{URL}/{a['id']}", json={"nombre": a["nombre"]}, headers=h).status_code == 200


def test_validaciones_422(api, usuarios):
    h = _auth(usuarios["admin"])
    assert api.post(URL, json={"nombre": "   ", "tipo": "insumo", "unidad": "lb"}, headers=h).status_code == 422
    assert api.post(URL, json={"nombre": _nombre(), "tipo": "otro", "unidad": "lb"}, headers=h).status_code == 422
    assert api.post(URL, json={"nombre": _nombre(), "tipo": "insumo", "unidad": " "}, headers=h).status_code == 422


def test_editar_y_auditoria_con_antes_y_despues(api, usuarios, S):
    item = _crear(api, usuarios)
    r = api.put(f"{URL}/{item['id']}", json={"tipo": "insumo", "unidad": "lb"}, headers=_auth(usuarios["gerente_general"]))
    assert r.status_code == 200
    assert r.json()["tipo"] == "insumo" and r.json()["unidad"] == "lb"
    s = S()
    filas = s.execute(select(AuditLog).where(
        AuditLog.entidad == "item_inventario", AuditLog.entidad_id == str(item["id"]),
    ).order_by(AuditLog.id)).scalars().all()
    s.close()
    assert [f.accion for f in filas] == ["INVENTARIO_ITEM_CREADO", "INVENTARIO_ITEM_ACTUALIZADO"]
    assert filas[1].detalle["antes"]["tipo"] == "vendible" and filas[1].detalle["despues"]["tipo"] == "insumo"


def test_desactivar_reactivar_e_inactivos_solo_para_gerencia(api, usuarios):
    item = _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    assert api.put(f"{URL}/{item['id']}", json={"activo": False}, headers=h).json()["activo"] is False
    ids_resp = {i["id"] for i in api.get(URL, params={"incluir_inactivos": True}, headers=_auth(usuarios["resp_tienda"])).json()}
    assert item["id"] not in ids_resp
    ids_ger = {i["id"] for i in api.get(URL, params={"incluir_inactivos": True}, headers=h).json()}
    assert item["id"] in ids_ger
    assert item["id"] not in {i["id"] for i in api.get(URL, headers=h).json()}
    assert api.put(f"{URL}/{item['id']}", json={"activo": True}, headers=h).json()["activo"] is True


def test_no_se_desactiva_si_esta_en_una_receta_activa(api, usuarios, S):
    item = _crear(api, usuarios)
    s = S()
    prod = ProductoMenu(nombre=f"Combo receta {uuid.uuid4().hex[:6]}", precio=50, categoria="combos", activo=True)
    s.add(prod)
    s.flush()
    s.add(ProductoComponente(producto_menu_id=prod.id, item_inventario_id=item["id"], cantidad=1))
    s.commit()
    pid, pnombre = prod.id, prod.nombre
    s.close()
    h = _auth(usuarios["admin"])
    r = api.put(f"{URL}/{item['id']}", json={"activo": False}, headers=h)
    assert r.status_code == 409
    assert pnombre in r.json()["detail"]
    assert api.delete(f"/api/config/productos/{pid}", headers=h).status_code == 200
    assert api.put(f"{URL}/{item['id']}", json={"activo": False}, headers=h).status_code == 200


def test_reordenar_renumera_y_audita(api, usuarios, S):
    _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    todos = api.get(URL, params={"incluir_inactivos": True}, headers=h).json()
    ids = [i["id"] for i in todos]
    nuevo = [ids[-1]] + ids[:-1]
    r = api.put(f"{URL}/orden", json={"ids": nuevo}, headers=h)
    assert r.status_code == 200
    despues = api.get(URL, params={"incluir_inactivos": True}, headers=h).json()
    assert [i["id"] for i in despues] == nuevo
    assert [i["orden_conteo"] for i in despues] == list(range(1, len(nuevo) + 1))
    s = S()
    fila = s.execute(select(AuditLog).where(AuditLog.accion == "INVENTARIO_ITEMS_ORDENADOS")
                     .order_by(AuditLog.id.desc())).scalars().first()
    s.close()
    assert fila.detalle["despues"] == nuevo


def test_reordenar_exige_todos_una_vez(api, usuarios):
    item = _crear(api, usuarios)
    h = _auth(usuarios["admin"])
    ids = [i["id"] for i in api.get(URL, params={"incluir_inactivos": True}, headers=h).json()]
    assert api.put(f"{URL}/orden", json={"ids": [item["id"]]}, headers=h).status_code == 400
    assert api.put(f"{URL}/orden", json={"ids": ids + [ids[0]]}, headers=h).status_code == 400
    assert api.put(f"{URL}/orden", json={"ids": ids + [999999999]}, headers=h).status_code == 400


def test_inexistente_da_404(api, usuarios):
    assert api.put(f"{URL}/999999999", json={"nombre": "X"}, headers=_auth(usuarios["admin"])).status_code == 404
