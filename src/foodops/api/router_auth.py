"""APIs de autenticación"""
import logging
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import (
    TokenData,
    create_access_token,
    get_current_user,
    oauth2_scheme,
    requiere_rol,
    verify_password,
    verify_token,
)
from foodops.core.config import settings
from foodops.db.models import Usuario
from foodops.domain.schemas import LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_MAX_INTENTOS = 5
_BLOQUEO_MINUTOS = 15


@router.post("/login", response_model=TokenResponse)
def login(request: Request, body: LoginRequest):
    """Login de usuario con rate limiting por intentos fallidos."""
    session = Session()
    _GENERIC_ERROR = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
    )
    client_ip = request.client.host if request.client else None
    try:
        stmt = select(Usuario).where(Usuario.username == body.username)
        usuario = session.execute(stmt).scalars().first()

        if not usuario:
            registrar_auditoria(
                session,
                accion="LOGIN_FALLIDO",
                entidad="usuario",
                detalle={"username": body.username, "motivo": "usuario_no_existe"},
                ip=client_ip,
            )
            session.commit()
            raise _GENERIC_ERROR

        # Check block
        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.utcnow():
            registrar_auditoria(
                session,
                accion="LOGIN_BLOQUEADO",
                entidad="usuario",
                entidad_id=usuario.id,
                usuario_id=usuario.id,
                punto_id=usuario.punto_id,
                detalle={"username": body.username},
                ip=client_ip,
            )
            session.commit()
            raise _GENERIC_ERROR

        if not verify_password(body.password, usuario.password_hash):
            usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
            if usuario.intentos_fallidos >= _MAX_INTENTOS:
                usuario.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=_BLOQUEO_MINUTOS)
            registrar_auditoria(
                session,
                accion="LOGIN_FALLIDO",
                entidad="usuario",
                entidad_id=usuario.id,
                usuario_id=usuario.id,
                punto_id=usuario.punto_id,
                detalle={"intentos": usuario.intentos_fallidos},
                ip=client_ip,
            )
            session.commit()
            raise _GENERIC_ERROR

        # Successful login: reset counters
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None

        access_token = create_access_token(
            data={
                "user_id": usuario.id,
                "username": usuario.username,
                "punto_id": usuario.punto_id or 0,
                "rol": usuario.rol.value,
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        session.commit()
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        logger.exception("Error inesperado en login")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
    finally:
        session.close()


@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    """Obtiene usuario actual desde el JWT."""
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "punto_id": current_user.punto_id,
        "rol": current_user.rol,
    }


@router.get("/usuarios")
def listar_usuarios(
    rol: Optional[str] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol("resp_tienda", "gerente_general", "admin")),
):
    """Lista usuarios activos del punto de venta del usuario autenticado (ej. repartidores)."""
    session = Session()
    try:
        stmt = select(Usuario).where(
            Usuario.punto_id == current_user.punto_id,
            Usuario.activo.is_(True),
        )
        if rol:
            stmt = stmt.where(Usuario.rol == rol)
        usuarios = session.execute(stmt).scalars().all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "nombre_completo": u.nombre_completo,
                "rol": u.rol.value,
            }
            for u in usuarios
        ]
    finally:
        session.close()
