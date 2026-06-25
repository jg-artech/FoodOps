"""APIs de autenticación"""

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta

from foodops.domain.schemas import LoginRequest, TokenResponse
from foodops.db.models import Usuario
from foodops.db.database import get_db
from foodops.core.auth import (
    create_access_token, 
    verify_password,
    TokenResponse as AuthTokenResponse
)
from foodops.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login de usuario"""
    
    stmt = select(Usuario).where(Usuario.username == request.username)
    result = await db.execute(stmt)
    usuario = result.scalars().first()
    
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

@router.get("/me")
async def get_me():
    """Obtiene usuario actual"""
    return {"message": "Endpoint para obtener usuario actual"}
