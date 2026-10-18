"""APIs de autenticación"""
import logging
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from foodops.core.audit import registrar_auditoria
from foodops.core.auth import (
    ROLES_MULTI_TIENDA,
    TokenData,
    create_access_token,
    get_current_user,
    hash_password,
    oauth2_scheme,
    requiere_rol,
    resolver_punto_id,
    usuario_ve_todas_las_tiendas,
    verify_password,
    verify_token,
)
from foodops.core.config import settings
from foodops.db.models import PuntoVenta, Usuario, UserRol
from foodops.domain.schemas import LoginRequest, TokenResponse, UsuarioCreate, UsuarioUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

_MAX_INTENTOS = 5
_BLOQUEO_MINUTOS = 15

# Crear/editar usuarios es más sensible que solo listarlos (GET /usuarios
# además deja entrar a resp_tienda, para que pueda ver sus repartidores).
_ROLES_GESTION_USUARIOS = ("admin", "gerente_general")


def _usuario_dict(u: Usuario, punto_nombre: Optional[str] = None) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "nombre_completo": u.nombre_completo,
        "rol": u.rol.value,
        "punto_id": u.punto_id,
        "punto_nombre": punto_nombre,
        "activo": u.activo,
    }


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
        # Case-insensitive: teclados móviles auto-capitalizan la primera letra
        # de inputs de texto salvo que el HTML lo desactive explícitamente, y
        # no todos los teclados/webviews lo respetan - comparar exacto rompía
        # el login desde celular con las mismas credenciales que sí funcionan
        # en PC (usuario quedaba "Admin" en vez de "admin").
        stmt = select(Usuario).where(func.lower(Usuario.username) == body.username.lower())
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

        # Un rol de tienda sin tienda asignada no puede operar: antes entraba
        # con punto_id 0 y todas sus consultas devolvían listas vacías sin
        # ningún error, que es peor que no dejarlo entrar.
        if usuario.punto_id is None and usuario.rol.value not in ROLES_MULTI_TIENDA:
            registrar_auditoria(
                session,
                accion="LOGIN_SIN_TIENDA",
                entidad="usuario",
                entidad_id=usuario.id,
                usuario_id=usuario.id,
                detalle={"rol": usuario.rol.value},
                ip=client_ip,
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Su usuario no tiene una tienda asignada, contacte al administrador",
            )

        # Successful login: reset counters
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None

        access_token = create_access_token(
            data={
                "user_id": usuario.id,
                "username": usuario.username,
                "punto_id": usuario.punto_id,
                "rol": usuario.rol.value,
                "empresa_id": usuario.empresa_id,
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
def get_me(current_user: TokenData = Depends(get_current_user)):
    """Usuario actual. Añade el nombre de su tienda y si ve todas, que es lo
    que el frontend usa para decidir si muestra el selector de tienda."""
    session = Session()
    try:
        punto = session.get(PuntoVenta, current_user.punto_id) if current_user.punto_id else None
        return {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "punto_id": current_user.punto_id,
            "punto_nombre": punto.nombre if punto else None,
            "rol": current_user.rol,
            "ve_todas_las_tiendas": usuario_ve_todas_las_tiendas(current_user),
        }
    finally:
        session.close()


@router.get("/usuarios")
def listar_usuarios(
    rol: Optional[str] = Query(default=None),
    punto_id: Optional[int] = Query(default=None),
    activo: Optional[bool] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol("resp_tienda", "gerente_general", "admin")),
):
    """Usuarios de la tienda del usuario autenticado.
    Gerencia puede pedir otra tienda con ?punto_id= u omitirlo para ver todas.
    Por defecto resp_tienda ve solo activos (uso operativo: elegir un
    repartidor); admin/gerente_general ven todos salvo que pasen ?activo=,
    porque la pantalla de gestión de usuarios también necesita ver a quién
    desactivó para poder reactivarlo."""
    session = Session()
    try:
        effective_punto_id = resolver_punto_id(session, current_user, punto_id, permitir_todas=True)
        stmt = select(Usuario)
        if activo is not None:
            stmt = stmt.where(Usuario.activo.is_(activo))
        elif current_user.rol == "resp_tienda":
            stmt = stmt.where(Usuario.activo.is_(True))
        if effective_punto_id is not None:
            stmt = stmt.where(Usuario.punto_id == effective_punto_id)
        if rol:
            stmt = stmt.where(Usuario.rol == rol)
        usuarios = session.execute(stmt.order_by(Usuario.id)).scalars().all()
        nombres_punto = {p.id: p.nombre for p in session.execute(select(PuntoVenta)).scalars()}
        return [_usuario_dict(u, nombres_punto.get(u.punto_id)) for u in usuarios]
    finally:
        session.close()


def _validar_rol_y_punto(session, rol_valor: str, punto_id: Optional[int]) -> UserRol:
    """Reglas compartidas por crear y actualizar usuario: rol válido, y
    punto_id presente+existente salvo que el rol sea de los que ven todas
    las tiendas (ver ROLES_MULTI_TIENDA en core.auth)."""
    rol_valores = {r.value: r for r in UserRol}
    if rol_valor not in rol_valores:
        raise HTTPException(status_code=400, detail=f"Rol inválido: '{rol_valor}'. Válidos: {', '.join(rol_valores)}")
    rol = rol_valores[rol_valor]

    if punto_id is not None:
        if session.get(PuntoVenta, punto_id) is None:
            raise HTTPException(status_code=404, detail="Punto de venta no encontrado")
    elif rol_valor not in ROLES_MULTI_TIENDA:
        raise HTTPException(
            status_code=400,
            detail=f"El rol '{rol_valor}' necesita una tienda asignada (no está entre los roles multitienda)",
        )
    return rol


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def crear_usuario(
    body: UsuarioCreate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GESTION_USUARIOS)),
):
    """Crea un usuario. Hasta ahora la única vía era scripts/crear_usuario.py
    a mano en el servidor; esto es lo mismo expuesto para el panel."""
    session = Session()
    try:
        rol = _validar_rol_y_punto(session, body.rol, body.punto_id)

        if session.execute(select(Usuario).where(Usuario.username == body.username)).scalars().first():
            raise HTTPException(status_code=400, detail=f"Ya existe un usuario con username '{body.username}'")
        if session.execute(select(Usuario).where(Usuario.email == body.email)).scalars().first():
            raise HTTPException(status_code=400, detail=f"Ya existe un usuario con email '{body.email}'")

        # empresa_id del usuario que crea, no del token: así un token emitido
        # antes del campo empresa_id (que queda None) no rompe esto.
        creador = session.get(Usuario, current_user.user_id)

        nuevo = Usuario(
            empresa_id=creador.empresa_id,
            punto_id=body.punto_id,
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
            nombre_completo=body.nombre_completo or body.username,
            rol=rol,
            activo=True,
        )
        session.add(nuevo)
        session.flush()

        punto = session.get(PuntoVenta, nuevo.punto_id) if nuevo.punto_id else None
        registrar_auditoria(
            session,
            accion="CREAR_USUARIO",
            entidad="usuario",
            entidad_id=nuevo.id,
            usuario_id=current_user.user_id,
            punto_id=nuevo.punto_id,
            detalle={"username": nuevo.username, "rol": rol.value},
        )
        session.commit()
        return _usuario_dict(nuevo, punto.nombre if punto else None)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()


@router.patch("/usuarios/{usuario_id}")
def actualizar_usuario(
    usuario_id: int,
    body: UsuarioUpdate,
    current_user: TokenData = Depends(requiere_rol(*_ROLES_GESTION_USUARIOS)),
):
    """Edita rol/tienda/estado/nombre, y opcionalmente resetea la contraseña
    (no hay pantalla de "cambiar mi contraseña" todavía, así que esta es la
    única vía si alguien se queda fuera)."""
    session = Session()
    try:
        usuario = session.get(Usuario, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        updates = body.model_dump(exclude_unset=True, exclude={"password"})

        if usuario_id == current_user.user_id and updates.get("activo") is False:
            raise HTTPException(status_code=400, detail="No puede desactivar su propio usuario")

        # rol y punto_id se validan juntos: si solo viene uno de los dos, se
        # completa con el valor actual para no dejar una combinación rota
        # (ej. cambiar el rol a uno de tienda sin tocar punto_id, cuando el
        # usuario no tenía tienda porque antes era gerente_general).
        rol_valor = updates.get("rol", usuario.rol.value)
        punto_id = updates["punto_id"] if "punto_id" in updates else usuario.punto_id
        if "rol" in updates or "punto_id" in updates:
            rol = _validar_rol_y_punto(session, rol_valor, punto_id)
            usuario.rol = rol
            usuario.punto_id = punto_id

        if "nombre_completo" in updates:
            usuario.nombre_completo = updates["nombre_completo"]
        if "activo" in updates:
            usuario.activo = updates["activo"]
        if body.password:
            usuario.password_hash = hash_password(body.password)

        punto = session.get(PuntoVenta, usuario.punto_id) if usuario.punto_id else None
        registrar_auditoria(
            session,
            accion="ACTUALIZAR_USUARIO",
            entidad="usuario",
            entidad_id=usuario.id,
            usuario_id=current_user.user_id,
            punto_id=usuario.punto_id,
            detalle={k: v for k, v in updates.items()} | ({"password_cambiada": True} if body.password else {}),
        )
        session.commit()
        return _usuario_dict(usuario, punto.nombre if punto else None)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()
