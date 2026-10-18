"""Panel de gestión de usuarios: crear, editar, RBAC.

Antes de este endpoint la única vía era scripts/crear_usuario.py a mano en
el servidor; estos tests cubren el equivalente expuesto por la API.
"""
import pytest
from sqlalchemy.orm import sessionmaker

from foodops.core.auth import create_access_token, hash_password
from foodops.db.models import Empresa, PuntoVenta, Usuario, UserRol


def _auth(usuario: dict) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data=usuario)}"}


@pytest.fixture(scope="module")
def datos(engine):
    Session = sessionmaker(bind=engine)
    s = Session()

    empresa = Empresa(nombre="Gestión Usuarios Test", nit="TEST-GU-1")
    s.add(empresa)
    s.flush()

    centro = PuntoVenta(empresa_id=empresa.id, nombre="Tienda GU Centro")
    s.add(centro)
    s.flush()

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
        return u

    admin = usuario("gu_admin", UserRol.ADMIN, None)
    resp_tienda = usuario("gu_resp_tienda", UserRol.RESP_TIENDA, centro)
    s.commit()

    def credenciales(u: Usuario) -> dict:
        return {
            "user_id": u.id,
            "username": u.username,
            "punto_id": u.punto_id,
            "rol": u.rol.value,
            "empresa_id": u.empresa_id,
        }

    out = {
        "centro": centro.id,
        "admin": credenciales(admin),
        "resp_tienda": credenciales(resp_tienda),
    }
    s.close()
    yield out


def test_admin_crea_usuario_de_tienda(api, datos):
    r = api.post(
        "/api/auth/usuarios",
        json={
            "username": "gu_nuevo_vendedor",
            "email": "gu_nuevo_vendedor@test.gt",
            "password": "Cambiar123!",
            "rol": "tomador_orden",
            "punto_id": datos["centro"],
        },
        headers=_auth(datos["admin"]),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["punto_id"] == datos["centro"]
    assert body["activo"] is True


def test_crear_rol_de_tienda_sin_punto_id_falla(api, datos):
    r = api.post(
        "/api/auth/usuarios",
        json={
            "username": "gu_sin_tienda",
            "email": "gu_sin_tienda@test.gt",
            "password": "Cambiar123!",
            "rol": "cocinero",
        },
        headers=_auth(datos["admin"]),
    )
    assert r.status_code == 400


def test_resp_tienda_no_puede_crear_usuarios(api, datos):
    """GET /usuarios sí deja entrar a resp_tienda (para ver repartidores de
    su tienda); crear uno es más sensible y queda solo para admin/GG."""
    r = api.post(
        "/api/auth/usuarios",
        json={
            "username": "gu_intento",
            "email": "gu_intento@test.gt",
            "password": "Cambiar123!",
            "rol": "cocinero",
            "punto_id": datos["centro"],
        },
        headers=_auth(datos["resp_tienda"]),
    )
    assert r.status_code == 403


def test_admin_desactiva_y_reactiva_usuario(api, datos):
    creado = api.post(
        "/api/auth/usuarios",
        json={
            "username": "gu_para_desactivar",
            "email": "gu_para_desactivar@test.gt",
            "password": "Cambiar123!",
            "rol": "tomador_orden",
            "punto_id": datos["centro"],
        },
        headers=_auth(datos["admin"]),
    ).json()

    r = api.patch(
        f"/api/auth/usuarios/{creado['id']}", json={"activo": False}, headers=_auth(datos["admin"])
    )
    assert r.status_code == 200
    assert r.json()["activo"] is False

    # Sigue existiendo para quien gestiona usuarios (no desaparece del panel).
    listado = api.get("/api/auth/usuarios", headers=_auth(datos["admin"])).json()
    assert any(u["id"] == creado["id"] and u["activo"] is False for u in listado)

    r = api.patch(
        f"/api/auth/usuarios/{creado['id']}", json={"activo": True}, headers=_auth(datos["admin"])
    )
    assert r.status_code == 200
    assert r.json()["activo"] is True


def test_admin_no_puede_desactivarse_a_si_mismo(api, datos):
    r = api.patch(
        f"/api/auth/usuarios/{datos['admin']['user_id']}",
        json={"activo": False},
        headers=_auth(datos["admin"]),
    )
    assert r.status_code == 400
