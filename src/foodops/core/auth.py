"""Authentication"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from foodops.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class TokenData(BaseModel):
    user_id: int
    username: str
    # NULL = sin tienda asignada. Solo es un estado válido para los roles que
    # ven todas las tiendas; para un rol de tienda el login lo rechaza.
    punto_id: Optional[int] = None
    rol: str
    # Añadido por el soporte multitienda. Optional para que un token emitido
    # antes del cambio siga siendo válido hasta expirar (ahí se omite la
    # validación de empresa, no se niega el acceso).
    empresa_id: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        username: str = payload.get("username")
        punto_id: Optional[int] = payload.get("punto_id")
        rol: str = payload.get("rol")
        empresa_id: Optional[int] = payload.get("empresa_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        # Tokens emitidos antes del multitienda usaban 0 como "sin tienda".
        if punto_id == 0:
            punto_id = None
        return TokenData(
            user_id=user_id,
            username=username,
            punto_id=punto_id,
            rol=rol,
            empresa_id=empresa_id,
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    return verify_token(token)


def requiere_rol(*roles_permitidos: str):
    """Dependency factory: 403 if current user's role is not in the allowed list."""
    def dependency(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.rol not in roles_permitidos:
            raise HTTPException(status_code=403, detail="No autorizado para este recurso")
        return current_user
    return dependency


# ---------------------------------------------------------------------------
# Alcance multitienda
# ---------------------------------------------------------------------------
#
# Única fuente de verdad sobre "qué tiendas puede tocar este usuario". Antes
# cada router tenía su propia copia de _resolve_punto_id, y los endpoints que
# cargaban un registro por id de URL no validaban nada (ver
# docs/AUDITORIA_MULTITIENDA.md, R1/R2).

# Ven y operan sobre todas las tiendas.
ROLES_TODAS_TIENDAS = ("gerente_general", "admin")
# Multitienda pero acotado a abastecimiento (sugerencias, pedidos, reglas).
ROLES_CENTRAL = ("gerente_central",)
ROLES_MULTI_TIENDA = ROLES_TODAS_TIENDAS + ROLES_CENTRAL


def usuario_ve_todas_las_tiendas(current_user: TokenData) -> bool:
    return current_user.rol in ROLES_MULTI_TIENDA


def _validar_punto_de_empresa(session, current_user: TokenData, punto_id: int) -> None:
    """El punto debe existir y ser de la empresa del usuario.

    Sin esto, un gerente_general podría leer datos de otra empresa de la
    plataforma pasando su punto_id. Hoy solo hay una empresa, pero el modelo
    es multiempresa desde el día uno.
    """
    from foodops.db.models import PuntoVenta  # local: evita ciclo de imports

    punto = session.get(PuntoVenta, punto_id)
    if punto is None:
        raise HTTPException(status_code=404, detail="Punto de venta no encontrado")
    if current_user.empresa_id is not None and punto.empresa_id != current_user.empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para esa tienda")


def resolver_punto_id(
    session,
    current_user: TokenData,
    punto_id: Optional[int] = None,
    *,
    permitir_todas: bool = False,
) -> Optional[int]:
    """Resuelve sobre qué tienda debe operar una consulta.

    - Rol de tienda: siempre su propia tienda. Pedir otra es 403 (antes se
      ignoraba en silencio, que esconde el intento en vez de registrarlo).
    - Rol multitienda sin punto_id: None ("todas") si permitir_todas, si no su
      propia tienda; si tampoco tiene, 400 pidiendo que especifique.
    - Rol multitienda con punto_id: se valida que exista y sea de su empresa.
    """
    if usuario_ve_todas_las_tiendas(current_user):
        if punto_id is None:
            if permitir_todas:
                return None
            if current_user.punto_id is not None:
                return current_user.punto_id
            raise HTTPException(
                status_code=400,
                detail="Indique punto_id: su usuario no tiene una tienda asignada",
            )
        _validar_punto_de_empresa(session, current_user, punto_id)
        return punto_id

    if current_user.punto_id is None:
        raise HTTPException(
            status_code=403,
            detail="Su usuario no tiene una tienda asignada, contacte al administrador",
        )
    if punto_id is not None and punto_id != current_user.punto_id:
        raise HTTPException(status_code=403, detail="No autorizado para esa tienda")
    return current_user.punto_id


def exigir_punto_propio(current_user: TokenData) -> int:
    """Tienda del usuario para endpoints de escritura que no aceptan selector.

    Un rol multitienda sin tienda asignada no puede, por ejemplo, abrir caja:
    no hay forma de saber de cuál.
    """
    if current_user.punto_id is None:
        raise HTTPException(
            status_code=400,
            detail="Su usuario no tiene una tienda asignada; esta operación requiere una tienda",
        )
    return current_user.punto_id


def exigir_acceso_a_punto(current_user: TokenData, punto_id_recurso: Optional[int]) -> None:
    """Valida que un registro ya cargado pertenezca a una tienda permitida.

    Se llama justo después de cada session.get(Modelo, id_de_la_url): sin esto
    el id de la URL es la única autorización, que es el IDOR cross-tienda.
    """
    if punto_id_recurso is None:
        return
    if usuario_ve_todas_las_tiendas(current_user):
        return
    if current_user.punto_id is None or punto_id_recurso != current_user.punto_id:
        raise HTTPException(status_code=403, detail="Este recurso pertenece a otra tienda")
