"""Impresión por agente de tienda + apertura de cajón.

Ver docs/DISENO_IMPRESION.md §2, §5, §6, §7 y §8.

Regla rectora (§8): la venta nunca se bloquea por la impresora. Todos los
endpoints de aquí solo encolan trabajos y responden de inmediato; ninguno
espera al agente. El cobro (POST /api/ordenes/, /transacciones/,
/confirmar-cobro) no depende de nada de este archivo.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, or_, and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from foodops.api.router_ordenes import _orden_dict
from foodops.core.audit import registrar_auditoria
from foodops.core.auth import (
    TokenData,
    exigir_acceso_a_punto,
    get_current_user,
    requiere_rol,
    resolver_punto_id,
)
from foodops.core.auth_agente import AgenteData, hash_token_agente, requiere_agente
from foodops.core.config import settings
from foodops.db.models import (
    TRABAJO_ESTADO_ERROR,
    TRABAJO_ESTADO_IMPRIMIENDO,
    TRABAJO_ESTADO_OK,
    TRABAJO_ESTADO_PENDIENTE,
    TRABAJO_TIPO_ABRIR_CAJON,
    TRABAJO_TIPO_TICKET,
    Orden,
    OrdenItem,
    PuntoVenta,
    TokenAgente,
    TrabajoImpresion,
    Usuario,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/impresion", tags=["impresion"])
# regenerar-token-agente cuelga de /api/puntos-venta (§7), no de /api/impresion.
router_puntos = APIRouter(prefix="/api/puntos-venta", tags=["impresion"])

engine = create_engine(settings.DATABASE_SYNC_URL)
Session = sessionmaker(bind=engine)

# ---------------------------------------------------------------------------
# Permisos (§2). Independientes de _ROLES_TIENDA de router_caja.py, que NO se
# toca: gerente_punto puede imprimir y abrir el CAJÓN físico, pero sigue sin
# poder abrir la CAJA financiera.
# ---------------------------------------------------------------------------

# Puede generar un trabajo TICKET.
ROLES_IMPRESION_TICKET = (
    "tomador_orden", "resp_tienda", "gerente_punto",
    "gerente_general", "admin",
)

# Puede generar un trabajo ABRIR_CAJON (automático vía confirmar-cobro, una
# sola vez por orden, o manual por el botón con motivo). tomador_orden fuera.
ROLES_ABRIR_CAJON = (
    "resp_tienda", "gerente_punto", "gerente_general", "admin",
)

# Ve el heartbeat del agente: _ROLES_TIENDA + gerente_punto (§7). Se escribe
# explícito para no importar ni modificar _ROLES_TIENDA.
ROLES_ESTADO_AGENTE = ("resp_tienda", "gerente_punto", "gerente_general", "admin")

# Emite/rota el token del agente.
ROLES_TOKEN_AGENTE = ("admin", "gerente_general")

# Un trabajo IMPRIMIENDO sin resultado tras este tiempo vuelve a entregarse
# (§5, decisión 6).
TIMEOUT_IMPRIMIENDO = timedelta(seconds=30)
# Agente "conectado" si hizo un request en esta ventana (§7, decisión 7).
VENTANA_CONEXION_AGENTE = timedelta(seconds=30)

MOTIVO_MIN_CARACTERES = 5


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TicketRequest(BaseModel):
    orden_id: int


class AbrirCajonRequest(BaseModel):
    # El mínimo de caracteres se valida en el handler, DESPUÉS del chequeo de
    # rol: así un tomador_orden siempre recibe 403 + audit_log, nunca un 422.
    motivo: str = Field(max_length=200)
    # Solo para roles multitienda sin tienda propia; un rol de tienda no
    # puede apuntar a otra (resolver_punto_id lo rechaza con 403).
    punto_id: Optional[int] = None


class ResultadoTrabajoRequest(BaseModel):
    estado: Literal["ok", "error"]
    error: Optional[str] = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trabajo_dict(t: TrabajoImpresion, incluir_payload: bool = False) -> dict:
    d = {
        "id": t.id,
        "punto_id": t.punto_id,
        "tipo": t.tipo,
        "estado": t.estado,
        "motivo": t.motivo,
        "orden_id": t.orden_id,
        "solicitado_por": t.solicitado_por,
        "created_at": str(t.created_at) if t.created_at else None,
        "tomado_at": str(t.tomado_at) if t.tomado_at else None,
        "completado_at": str(t.completado_at) if t.completado_at else None,
        "error": t.error,
    }
    if incluir_payload:
        d["payload"] = t.payload
    return d


def _nombre_usuario(session, usuario_id: Optional[int]) -> Optional[str]:
    if usuario_id is None:
        return None
    u = session.get(Usuario, usuario_id)
    return (u.nombre_completo or u.username) if u else None


def _payload_ticket(session, orden: Orden, punto: PuntoVenta) -> dict:
    """JSON estructurado para el agente, NUNCA HTML (§9.1).

    Mismos campos que _orden_dict (lo que hoy usa ticket.js en el navegador);
    el agente es quien lo convierte a ESC/POS.
    """
    items = session.execute(
        select(OrdenItem).where(OrdenItem.orden_id == orden.id).order_by(OrdenItem.id)
    ).scalars().all()
    return {
        "version": 1,
        "orden": _orden_dict(
            orden,
            items,
            tomada_por_nombre=_nombre_usuario(session, orden.tomada_por),
            punto_nombre=punto.nombre,
            confirmado_por_nombre=_nombre_usuario(session, orden.confirmado_por),
        ),
    }


def _get_punto_activo(session, punto_id: int) -> PuntoVenta:
    punto = session.get(PuntoVenta, punto_id)
    if punto is None or not punto.activo:
        raise HTTPException(status_code=404, detail="Punto de venta no encontrado")
    return punto


# ---------------------------------------------------------------------------
# Endpoints del agente (token de tienda, §6)
# ---------------------------------------------------------------------------

@router.get("/agente/pendientes")
def agente_pendientes(agente: AgenteData = Depends(requiere_agente)):
    """Entrega los trabajos PENDIENTE (o IMPRIMIENDO vencidos hace +30s) de la
    tienda del token y los marca IMPRIMIENDO en la misma transacción.

    FOR UPDATE SKIP LOCKED: si por error corren dos agentes con el mismo
    token, no reciben el mismo trabajo a la vez.
    """
    session = Session()
    try:
        ahora = datetime.utcnow()
        limite = ahora - TIMEOUT_IMPRIMIENDO
        trabajos = session.execute(
            select(TrabajoImpresion)
            .where(
                TrabajoImpresion.punto_id == agente.punto_id,
                or_(
                    TrabajoImpresion.estado == TRABAJO_ESTADO_PENDIENTE,
                    and_(
                        TrabajoImpresion.estado == TRABAJO_ESTADO_IMPRIMIENDO,
                        or_(
                            TrabajoImpresion.tomado_at.is_(None),
                            TrabajoImpresion.tomado_at < limite,
                        ),
                    ),
                ),
            )
            .order_by(TrabajoImpresion.id)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).scalars().all()

        for t in trabajos:
            t.estado = TRABAJO_ESTADO_IMPRIMIENDO
            t.tomado_at = ahora
        session.commit()
        return [_trabajo_dict(t, incluir_payload=True) for t in trabajos]
    finally:
        session.close()


@router.post("/agente/trabajos/{trabajo_id}/resultado")
def agente_resultado(
    trabajo_id: int,
    body: ResultadoTrabajoRequest,
    agente: AgenteData = Depends(requiere_agente),
):
    session = Session()
    try:
        trabajo = session.get(TrabajoImpresion, trabajo_id)
        # 404 también si es de otra tienda: no revela que el id existe.
        if trabajo is None or trabajo.punto_id != agente.punto_id:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        if trabajo.estado != TRABAJO_ESTADO_IMPRIMIENDO:
            raise HTTPException(
                status_code=409,
                detail=f"El trabajo está en estado '{trabajo.estado}', no 'imprimiendo'",
            )

        trabajo.estado = TRABAJO_ESTADO_OK if body.estado == "ok" else TRABAJO_ESTADO_ERROR
        trabajo.error = body.error if body.estado == "error" else None
        trabajo.completado_at = datetime.utcnow()

        if trabajo.estado == TRABAJO_ESTADO_ERROR:
            registrar_auditoria(
                session,
                accion="FALLO_IMPRESION",
                entidad="trabajo_impresion",
                entidad_id=trabajo.id,
                punto_id=trabajo.punto_id,
                detalle={"tipo": trabajo.tipo, "orden_id": trabajo.orden_id, "error": body.error},
            )
        session.commit()
        return _trabajo_dict(trabajo)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Endpoints de usuario (JWT normal)
# ---------------------------------------------------------------------------

@router.get("/agente/estado")
def agente_estado(
    punto_id: Optional[int] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*ROLES_ESTADO_AGENTE)),
):
    """Heartbeat: conectado = el agente hizo un request en los últimos 30s."""
    session = Session()
    try:
        punto_id = resolver_punto_id(session, current_user, punto_id)
        token = session.execute(
            select(TokenAgente).where(
                TokenAgente.punto_id == punto_id, TokenAgente.activo.is_(True)
            )
        ).scalar_one_or_none()
        ultima = token.ultima_conexion_at if token else None
        conectado = ultima is not None and datetime.utcnow() - ultima <= VENTANA_CONEXION_AGENTE
        return {
            "punto_id": punto_id,
            "tiene_token": token is not None,
            "conectado": conectado,
            "ultima_conexion_at": str(ultima) if ultima else None,
        }
    finally:
        session.close()


@router.post("/ticket", status_code=201)
def crear_trabajo_ticket(
    body: TicketRequest,
    current_user: TokenData = Depends(requiere_rol(*ROLES_IMPRESION_TICKET)),
):
    """Encola un TICKET. NUNCA crea ABRIR_CAJON: imprimir o reimprimir no
    abre el cajón bajo ninguna circunstancia (§7)."""
    session = Session()
    try:
        orden = session.get(Orden, body.orden_id)
        if orden is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        exigir_acceso_a_punto(current_user, orden.punto_id)

        punto = _get_punto_activo(session, orden.punto_id)
        if not punto.impresora_activa:
            # El frontend cae al window.print() de siempre.
            raise HTTPException(
                status_code=409, detail="Esta tienda no tiene impresora por agente activa"
            )

        trabajo = TrabajoImpresion(
            punto_id=orden.punto_id,
            tipo=TRABAJO_TIPO_TICKET,
            payload=_payload_ticket(session, orden, punto),
            estado=TRABAJO_ESTADO_PENDIENTE,
            solicitado_por=current_user.user_id,
            orden_id=orden.id,
        )
        session.add(trabajo)
        session.commit()
        return _trabajo_dict(trabajo)
    except HTTPException:
        session.rollback()
        raise
    finally:
        session.close()


@router.post("/abrir-cajon", status_code=201)
def abrir_cajon_manual(
    body: AbrirCajonRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Botón manual "Abrir cajón" (físico). Ruta abrir-cajon, no abrir-caja:
    abrir-caja es la apertura financiera del día en router_caja.py."""
    session = Session()
    try:
        if current_user.rol == "tomador_orden":
            registrar_auditoria(
                session,
                accion="INTENTO_ABRIR_CAJON_DENEGADO",
                entidad="punto_venta",
                entidad_id=current_user.punto_id,
                usuario_id=current_user.user_id,
                punto_id=current_user.punto_id,
                detalle={"rol": current_user.rol, "motivo": body.motivo},
            )
            session.commit()
            raise HTTPException(status_code=403, detail="No autorizado para abrir el cajón")
        if current_user.rol not in ROLES_ABRIR_CAJON:
            raise HTTPException(status_code=403, detail="No autorizado para abrir el cajón")

        motivo = body.motivo.strip()
        if len(motivo) < MOTIVO_MIN_CARACTERES:
            raise HTTPException(
                status_code=422,
                detail=f"El motivo debe tener al menos {MOTIVO_MIN_CARACTERES} caracteres",
            )

        punto_id = resolver_punto_id(session, current_user, body.punto_id)
        punto = _get_punto_activo(session, punto_id)
        if not punto.cajon_activo:
            raise HTTPException(status_code=409, detail="Esta tienda no tiene el cajón activo")

        trabajo = TrabajoImpresion(
            punto_id=punto_id,
            tipo=TRABAJO_TIPO_ABRIR_CAJON,
            payload={},
            estado=TRABAJO_ESTADO_PENDIENTE,
            solicitado_por=current_user.user_id,
            motivo=motivo,
        )
        session.add(trabajo)
        session.flush()
        registrar_auditoria(
            session,
            accion="ABRIR_CAJON_MANUAL",
            entidad="trabajo_impresion",
            entidad_id=trabajo.id,
            usuario_id=current_user.user_id,
            punto_id=punto_id,
            detalle={"motivo": motivo},
        )
        session.commit()
        return _trabajo_dict(trabajo)
    except HTTPException:
        # El audit del intento denegado ya se confirmó antes del raise.
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/trabajos")
def listar_trabajos(
    punto_id: Optional[int] = Query(default=None),
    orden_id: Optional[int] = Query(default=None),
    estado: Optional[Literal["pendiente", "imprimiendo", "ok", "error"]] = Query(default=None),
    current_user: TokenData = Depends(requiere_rol(*ROLES_IMPRESION_TICKET)),
):
    session = Session()
    try:
        punto_id = resolver_punto_id(session, current_user, punto_id, permitir_todas=True)
        stmt = select(TrabajoImpresion).order_by(TrabajoImpresion.id.desc()).limit(100)
        if punto_id is not None:
            stmt = stmt.where(TrabajoImpresion.punto_id == punto_id)
        if orden_id is not None:
            stmt = stmt.where(TrabajoImpresion.orden_id == orden_id)
        if estado is not None:
            stmt = stmt.where(TrabajoImpresion.estado == estado)
        return [_trabajo_dict(t) for t in session.execute(stmt).scalars().all()]
    finally:
        session.close()


@router.post("/trabajos/{trabajo_id}/reintentar")
def reintentar_trabajo(
    trabajo_id: int,
    current_user: TokenData = Depends(requiere_rol(*ROLES_IMPRESION_TICKET)),
):
    """Solo trabajos en ERROR. Vuelve a PENDIENTE con el mismo id y
    created_at (trazabilidad). Puede quien lo creó o la gerencia de esa
    tienda; un ABRIR_CAJON solo lo reintenta un rol de ROLES_ABRIR_CAJON."""
    session = Session()
    try:
        trabajo = session.get(TrabajoImpresion, trabajo_id)
        if trabajo is None:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        exigir_acceso_a_punto(current_user, trabajo.punto_id)

        es_gerencia = current_user.rol in ROLES_ABRIR_CAJON
        if trabajo.tipo == TRABAJO_TIPO_ABRIR_CAJON and not es_gerencia:
            raise HTTPException(status_code=403, detail="No autorizado para abrir el cajón")
        if not es_gerencia and trabajo.solicitado_por != current_user.user_id:
            raise HTTPException(status_code=403, detail="Solo quien lo creó o la gerencia")
        if trabajo.estado != TRABAJO_ESTADO_ERROR:
            raise HTTPException(status_code=409, detail="Solo se reintentan trabajos en error")
        if trabajo.tipo == TRABAJO_TIPO_ABRIR_CAJON:
            punto = _get_punto_activo(session, trabajo.punto_id)
            if not punto.cajon_activo:
                raise HTTPException(status_code=409, detail="Esta tienda no tiene el cajón activo")

        trabajo.estado = TRABAJO_ESTADO_PENDIENTE
        trabajo.error = None
        trabajo.tomado_at = None
        trabajo.completado_at = None
        registrar_auditoria(
            session,
            accion="REINTENTAR_TRABAJO_IMPRESION",
            entidad="trabajo_impresion",
            entidad_id=trabajo.id,
            usuario_id=current_user.user_id,
            punto_id=trabajo.punto_id,
            detalle={"tipo": trabajo.tipo, "orden_id": trabajo.orden_id},
        )
        session.commit()
        return _trabajo_dict(trabajo)
    except HTTPException:
        session.rollback()
        raise
    finally:
        session.close()


@router_puntos.post("/{punto_id}/regenerar-token-agente")
def regenerar_token_agente(
    punto_id: int,
    response: Response,
    current_user: TokenData = Depends(requiere_rol(*ROLES_TOKEN_AGENTE)),
):
    """Emite un token nuevo y revoca el anterior en la misma transacción.

    El token en claro se devuelve UNA sola vez; en BD solo queda su sha256.
    Nunca se escribe en logs ni en audit_log.
    """
    session = Session()
    try:
        resolver_punto_id(session, current_user, punto_id)
        _get_punto_activo(session, punto_id)

        ahora = datetime.utcnow()
        revocados = session.execute(
            update(TokenAgente)
            .where(TokenAgente.punto_id == punto_id, TokenAgente.activo.is_(True))
            .values(activo=False, revocado_at=ahora)
        ).rowcount
        # Flush explícito: la revocación tiene que llegar a la BD antes del
        # INSERT por el índice único parcial (un token activo por tienda).
        session.flush()

        token_claro = secrets.token_urlsafe(32)
        nuevo = TokenAgente(
            punto_id=punto_id,
            token_hash=hash_token_agente(token_claro),
            activo=True,
            creado_por=current_user.user_id,
            created_at=ahora,
        )
        session.add(nuevo)
        session.flush()

        registrar_auditoria(
            session,
            accion="REGENERAR_TOKEN_AGENTE",
            entidad="token_agente",
            entidad_id=nuevo.id,
            usuario_id=current_user.user_id,
            punto_id=punto_id,
            detalle={"tokens_revocados": revocados},
        )
        session.commit()

        response.headers["Cache-Control"] = "no-store"
        return {
            "punto_id": punto_id,
            "token_id": nuevo.id,
            "token": token_claro,
            "aviso": "Copie este token ahora: no se volverá a mostrar.",
        }
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Otra regeneración de token está en curso, intente de nuevo"
        )
    except HTTPException:
        session.rollback()
        raise
    finally:
        session.close()
