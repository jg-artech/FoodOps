"""APIs de autenticación"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import os
from datetime import timedelta

from fastapi.security import OAuth2PasswordBearer
from foodops.domain.schemas import LoginRequest, TokenResponse
from foodops.db.models import Usuario
from foodops.core.auth import create_access_token, verify_password, verify_token
from foodops.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Usar sync en lugar de async
engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """Login de usuario"""
    session = Session()
    try:
        stmt = select(Usuario).where(Usuario.username == request.username)
        usuario = session.execute(stmt).scalars().first()
        
        if not usuario or not verify_password(request.password, usuario.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos"
            )
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "user_id": usuario.id,
                "username": usuario.username,
                "punto_id": usuario.punto_id or 0,
                "rol": usuario.rol.value
            },
            expires_delta=access_token_expires
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        session.close()

@router.get("/me")
def get_me(token: str = Depends(oauth2_scheme)):
    """Obtiene usuario actual desde el JWT"""
    user = verify_token(token)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "punto_id": user.punto_id,
        "rol": user.rol
    }
