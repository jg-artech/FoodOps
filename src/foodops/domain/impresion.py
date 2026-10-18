"""Lógica de impresión compartida entre routers.

Vive aquí y no en router_impresion.py para que router_ordenes.py pueda
encolar el ABRIR_CAJON automático sin un import circular (router_impresion
ya importa de router_ordenes).
"""
import logging
from typing import Optional

from sqlalchemy import select

from foodops.core.audit import registrar_auditoria
from foodops.db.models import (
    MOTIVO_CAJON_COBRO_EFECTIVO,
    TRABAJO_ESTADO_PENDIENTE,
    TRABAJO_TIPO_ABRIR_CAJON,
    Orden,
    PuntoVenta,
    TrabajoImpresion,
)

logger = logging.getLogger(__name__)


def encolar_cajon_por_cobro(session, orden: Orden, usuario_id: int) -> Optional[TrabajoImpresion]:
    """Encola el ABRIR_CAJON automático de una orden en efectivo recién cobrada.

    - Solo si la tienda tiene cajon_activo.
    - Una sola vez por orden: si ya existe un ABRIR_CAJON con ese orden_id no
      crea otro (además hay un índice único parcial en la BD).
    - Nunca bloquea el cobro (docs/DISENO_IMPRESION.md §8): corre en un
      SAVEPOINT y cualquier error se registra en el log y se descarta, sin
      tocar lo que el llamador ya escribió en la sesión.

    Devuelve el trabajo creado, o None si no se creó.
    """
    try:
        with session.begin_nested():
            punto = session.get(PuntoVenta, orden.punto_id)
            if punto is None or not punto.cajon_activo:
                return None

            ya_existe = session.execute(
                select(TrabajoImpresion.id).where(
                    TrabajoImpresion.orden_id == orden.id,
                    TrabajoImpresion.tipo == TRABAJO_TIPO_ABRIR_CAJON,
                )
            ).first()
            if ya_existe:
                return None

            trabajo = TrabajoImpresion(
                punto_id=orden.punto_id,
                tipo=TRABAJO_TIPO_ABRIR_CAJON,
                payload={},
                estado=TRABAJO_ESTADO_PENDIENTE,
                solicitado_por=usuario_id,
                motivo=MOTIVO_CAJON_COBRO_EFECTIVO,
                orden_id=orden.id,
            )
            session.add(trabajo)
            session.flush()

            registrar_auditoria(
                session,
                accion="ABRIR_CAJON_AUTOMATICO",
                entidad="trabajo_impresion",
                entidad_id=trabajo.id,
                usuario_id=usuario_id,
                punto_id=orden.punto_id,
                detalle={"orden_id": orden.id, "numero_orden": orden.numero_orden},
            )
            return trabajo
    except Exception:
        logger.exception("No se pudo encolar ABRIR_CAJON para la orden %s", orden.id)
        return None
