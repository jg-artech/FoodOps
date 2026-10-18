"""Autenticación del agente de impresión de tienda.

Espacio de autenticación separado del JWT de usuarios (docs/DISENO_IMPRESION.md
§6): el agente manda `Authorization: Bearer <token>`, el backend busca el
sha256 de ese token entre los tokens activos y de ahí deriva la tienda. El
agente nunca manda su propio punto_id.

SHA-256 y no bcrypt: el token es aleatorio de 256 bits (no adivinable aunque
el hash sea rápido) y el agente hace polling cada pocos segundos.
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from foodops.core.config import settings
from foodops.db.models import TokenAgente

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

# auto_error=False: sin header devolvemos 401 (HTTPBearer daría 403).
_bearer = HTTPBearer(auto_error=False)



def _no_autorizado() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Token de agente inválido o revocado",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class AgenteData:
    token_id: int
    punto_id: int


def hash_token_agente(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def requiere_agente(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AgenteData:
    """Valida el token del agente y actualiza su heartbeat.

    401 si falta, no existe o está revocado. Como efecto lateral, cada request
    válido actualiza ultima_conexion_at (heartbeat, decisión 7 de §11).
    """
    if credenciales is None or not credenciales.credentials:
        raise _no_autorizado()

    session = Session()
    try:
        token = session.execute(
            select(TokenAgente).where(
                TokenAgente.token_hash == hash_token_agente(credenciales.credentials),
                TokenAgente.activo.is_(True),
            )
        ).scalar_one_or_none()
        if token is None:
            raise _no_autorizado()

        token.ultima_conexion_at = datetime.utcnow()
        session.commit()
        return AgenteData(token_id=token.id, punto_id=token.punto_id)
    finally:
        session.close()
