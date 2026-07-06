"""Audit log helper"""
from typing import Any, Optional
from sqlalchemy.orm import Session
from foodops.db.models import AuditLog


def registrar_auditoria(
    session: Session,
    accion: str,
    entidad: str,
    entidad_id: Optional[Any] = None,
    usuario_id: Optional[int] = None,
    punto_id: Optional[int] = None,
    detalle: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    """Insert an audit record into the current session (caller commits)."""
    log = AuditLog(
        usuario_id=usuario_id,
        punto_id=punto_id,
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        detalle=detalle,
        ip=ip,
    )
    session.add(log)
    session.flush()
