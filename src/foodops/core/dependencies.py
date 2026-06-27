"""FastAPI dependencies"""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from foodops.core.auth import verify_token, TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    return verify_token(token)

async def get_current_admin_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo admins permitidos")
    return current_user
