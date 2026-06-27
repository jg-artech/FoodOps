"""Seed data inicial para entornos demo/desarrollo."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from foodops.core.auth import hash_password
from foodops.db.models import Empresa, PuntoVenta, UserRol, Usuario


DEMO_EMPRESA_NIT = "CF-FOODOPS-QSR"


@dataclass(frozen=True)
class SeedResult:
    created: bool
    empresa_nit: str
    puntos_venta: int
    usuarios: int


def build_demo_seed_data() -> dict:
    """Construye datos demo deterministas para pruebas y desarrollo local."""

    return {
        "empresa": {
            "nombre": "FoodOps Demo QSR",
            "nit": DEMO_EMPRESA_NIT,
            "registro_tributario": "RTU-DEMO",
            "telefono": "+502 2222-0101",
            "email": "admin@foodops.gt",
            "direccion": "Ciudad de Guatemala, Guatemala",
        },
        "puntos_venta": [
            {
                "nombre": "Sucursal Zona 10",
                "direccion": "Zona 10, Ciudad de Guatemala",
                "telefono": "+502 2222-0102",
            },
            {
                "nombre": "Sucursal Cayala",
                "direccion": "Ciudad Cayala, Guatemala",
                "telefono": "+502 2222-0103",
            },
        ],
        "usuarios": [
            {
                "username": "admin_demo",
                "email": "admin.demo@foodops.gt",
                "password": "FoodOps123!",
                "nombre_completo": "Administrador Demo",
                "rol": UserRol.ADMIN,
                "punto_nombre": None,
            },
            {
                "username": "caja_z10",
                "email": "caja.z10@foodops.gt",
                "password": "FoodOps123!",
                "nombre_completo": "Caja Zona 10",
                "rol": UserRol.TOMADOR_ORDEN,
                "punto_nombre": "Sucursal Zona 10",
            },
            {
                "username": "cocina_z10",
                "email": "cocina.z10@foodops.gt",
                "password": "FoodOps123!",
                "nombre_completo": "Cocina Zona 10",
                "rol": UserRol.COCINERO,
                "punto_nombre": "Sucursal Zona 10",
            },
            {
                "username": "gerente_cayala",
                "email": "gerente.cayala@foodops.gt",
                "password": "FoodOps123!",
                "nombre_completo": "Gerente Cayala",
                "rol": UserRol.GERENTE_PUNTO,
                "punto_nombre": "Sucursal Cayala",
            },
        ],
    }


async def seed_demo_data(db: AsyncSession) -> SeedResult:
    """Inserta datos demo si no existen previamente."""

    data = build_demo_seed_data()
    empresa_data = data["empresa"]

    existing_empresa = await db.scalar(
        select(Empresa).where(Empresa.nit == empresa_data["nit"])
    )
    if existing_empresa:
        return SeedResult(
            created=False,
            empresa_nit=empresa_data["nit"],
            puntos_venta=0,
            usuarios=0,
        )

    try:
        empresa = Empresa(**empresa_data)
        db.add(empresa)
        await db.flush()

        puntos_por_nombre: dict[str, PuntoVenta] = {}
        for punto_data in data["puntos_venta"]:
            punto = PuntoVenta(empresa_id=empresa.id, **punto_data)
            db.add(punto)
            puntos_por_nombre[punto.nombre] = punto

        await db.flush()

        for raw_usuario_data in data["usuarios"]:
            usuario_data = raw_usuario_data.copy()
            punto_nombre = usuario_data.pop("punto_nombre")
            password = usuario_data.pop("password")
            punto = puntos_por_nombre.get(punto_nombre) if punto_nombre else None
            usuario = Usuario(
                empresa_id=empresa.id,
                punto_id=punto.id if punto else None,
                password_hash=hash_password(password),
                **usuario_data,
            )
            db.add(usuario)

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return SeedResult(
        created=True,
        empresa_nit=empresa_data["nit"],
        puntos_venta=len(data["puntos_venta"]),
        usuarios=len(data["usuarios"]),
    )
