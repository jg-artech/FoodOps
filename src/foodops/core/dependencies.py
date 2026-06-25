"""FastAPI dependencies"""

from src.foodops.core.auth import get_current_user, TokenData

async def get_current_admin_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Valida que sea admin"""
    if current_user.rol != "admin":
        raise PermissionError("Solo admins permitidos")
    return current_user
