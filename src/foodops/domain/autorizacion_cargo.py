"""Autorización de un responsable para un cargo de entrega sobre el tope.

Flujo (decisión 2 de la fase de cargo de entrega):
1. El responsable escribe su usuario y contraseña en la pantalla del vendedor.
   POST /api/auth/autorizar-cargo-entrega verifica las credenciales, con el
   mismo bloqueo por intentos fallidos que el login, y emite un token.
2. El token dura 5 minutos y queda atado a la tienda, al monto exacto y al
   responsable que autorizó.
3. POST /api/ordenes/ lo recibe en autorizacion_cargo y lo consume una sola
   vez: el jti se guarda en autorizaciones_cargo_usadas dentro de la misma
   transacción que la orden (si la orden falla, el token no se gasta).

El token se firma con una clave DERIVADA de SECRET_KEY, distinta de la del
token de sesión: un token de sesión no sirve como autorización y una
autorización no sirve como sesión, aunque alguien cambie el "typ".
"""
import hashlib
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.exc import IntegrityError

from foodops.core.auth import ROLES_TODAS_TIENDAS
from foodops.core.config import settings
from foodops.db.models import AutorizacionCargoUsada, Usuario

TYP = "autorizacion_cargo_entrega"
VIGENCIA = timedelta(minutes=5)

# Mismo conjunto que _ROLES_CONFIRMAR_COBRO de router_ordenes.py (no se
# importa de allí porque ese módulo importa este). Una prueba verifica que
# coincidan.
ROLES_AUTORIZAN_CARGO = ("resp_tienda", "gerente_punto", "gerente_general", "admin")

# 403 y no 401: el frontend cierra la sesión del VENDEDOR ante cualquier 401
# (services/api.js), y aquí quien se equivocó es el responsable.
_NO_AUTORIZADO = 403


def _clave() -> str:
    return hashlib.sha256(f"{TYP}:{settings.SECRET_KEY}".encode()).hexdigest()


def monto_texto(monto) -> str:
    """Monto canónico con 2 decimales ("25.00"): así se compara exacto, sin
    las sorpresas de float."""
    return str(Decimal(str(monto)).quantize(Decimal("0.01")))


def responsable_puede_autorizar(responsable: Usuario, punto_id: int) -> Optional[str]:
    """None si puede; si no, el motivo (para el log, no para el usuario)."""
    if not responsable.activo:
        return "inactivo"
    if responsable.rol.value not in ROLES_AUTORIZAN_CARGO:
        return "rol_sin_permiso"
    if responsable.rol.value not in ROLES_TODAS_TIENDAS and responsable.punto_id != punto_id:
        return "otra_tienda"
    return None


def emitir(responsable: Usuario, *, punto_id: int, monto, solicitado_por: int) -> dict:
    ahora = datetime.utcnow()
    exp = ahora + VIGENCIA
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "typ": TYP,
            "jti": jti,
            "sub": str(responsable.id),
            "punto_id": punto_id,
            "monto": monto_texto(monto),
            "solicitado_por": solicitado_por,
            "iat": ahora,
            "exp": exp,
        },
        _clave(),
        algorithm=settings.ALGORITHM,
    )
    return {"token": token, "jti": jti, "expira_at": exp}


def validar_y_consumir(session, token: str, *, punto_id: int, monto, usuario_id: int, orden_id: int) -> int:
    """Valida el token contra la orden y lo marca como usado en la sesión
    actual (sin commit: lo confirma la transacción de la orden).

    Devuelve el id del responsable que autorizó. Cualquier problema: 403.
    """
    try:
        datos = jwt.decode(token, _clave(), algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(_NO_AUTORIZADO, "La autorización del responsable venció; pídela de nuevo")
    except JWTError:
        raise HTTPException(_NO_AUTORIZADO, "Autorización del responsable inválida")

    if datos.get("typ") != TYP or not datos.get("jti") or not datos.get("sub"):
        raise HTTPException(_NO_AUTORIZADO, "Autorización del responsable inválida")
    if datos.get("punto_id") != punto_id:
        raise HTTPException(_NO_AUTORIZADO, "La autorización es de otra tienda")
    if datos.get("monto") != monto_texto(monto):
        raise HTTPException(
            _NO_AUTORIZADO,
            f"El cargo de entrega no coincide con el autorizado (Q{datos.get('monto')})",
        )

    # El responsable tiene que seguir pudiendo autorizar al momento de usarla
    # (por ejemplo, no haber sido desactivado en esos 5 minutos).
    responsable = session.get(Usuario, int(datos["sub"]))
    if responsable is None or responsable_puede_autorizar(responsable, punto_id):
        raise HTTPException(_NO_AUTORIZADO, "El responsable que autorizó ya no puede hacerlo")

    # Uso único: la PK sobre jti rechaza el segundo intento, incluso si dos
    # órdenes llegan a la vez con el mismo token. SAVEPOINT para que el
    # choque no tumbe la transacción de la orden antes de responder el 403.
    try:
        with session.begin_nested():
            session.add(
                AutorizacionCargoUsada(
                    jti=datos["jti"],
                    orden_id=orden_id,
                    punto_id=punto_id,
                    autorizado_por=responsable.id,
                    usado_por=usuario_id,
                    monto=Decimal(datos["monto"]),
                    usado_at=datetime.utcnow(),
                )
            )
    except IntegrityError:
        raise HTTPException(_NO_AUTORIZADO, "Esta autorización ya fue usada; pide una nueva")

    return responsable.id
