"""Utilidades de fecha/hora"""
from datetime import date, datetime, timedelta, timezone


def local_day_bounds(fecha: date) -> tuple[datetime, datetime]:
    """Rango [inicio, fin) de un día calendario LOCAL, expresado como datetimes
    naive-UTC comparables contra columnas pobladas con datetime.utcnow().

    Necesario porque date.today() usa la zona horaria local del servidor
    (America/Guatemala, UTC-6) mientras que created_at/updated_at se guardan
    en UTC vía datetime.utcnow(). Comparar un rango naive construido
    directamente desde `fecha` (sin este ajuste) contra timestamps UTC excluye
    silenciosamente cualquier registro creado después de las 18:00 hora local
    (que ya cae en el día UTC siguiente) - un bug real que afectaba el cálculo
    de efectivo_esperado y consumo_teórico en horas de la tarde/noche.
    """
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime(fecha.year, fecha.month, fecha.day, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


# Guatemala no tiene horario de verano: UTC-6 todo el año. Se usa un desfase
# fijo para no depender de la zona horaria del servidor o del contenedor
# (local_day_bounds sí depende de ella).
ZONA_GUATEMALA = timezone(timedelta(hours=-6), "America/Guatemala")


def limites_hoy_guatemala(ahora_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """Rango [inicio, fin) del día de hoy en Guatemala, como datetimes
    naive-UTC comparables con columnas pobladas con datetime.utcnow()."""
    if ahora_utc is None:
        ahora_utc = datetime.now(timezone.utc)
    elif ahora_utc.tzinfo is None:
        ahora_utc = ahora_utc.replace(tzinfo=timezone.utc)
    hoy = ahora_utc.astimezone(ZONA_GUATEMALA).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, tzinfo=ZONA_GUATEMALA)
    fin = inicio + timedelta(days=1)
    return (
        inicio.astimezone(timezone.utc).replace(tzinfo=None),
        fin.astimezone(timezone.utc).replace(tzinfo=None),
    )
