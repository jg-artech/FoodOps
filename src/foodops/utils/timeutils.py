"""Utilidades de fecha/hora: el día local del negocio, en un solo lugar.

Las columnas created_at/updated_at se guardan en UTC naive
(datetime.utcnow()). El "día" del negocio es el de Guatemala. Antes, la caja
usaba la zona del servidor (date.today() y datetime.now().astimezone()) y el
listado del vendedor un UTC-6 propio: en un contenedor en UTC los dos días
no coincidían después de las 18:00. Todo lo que necesite "hoy" o los límites
de un día debe pasar por aquí.
"""
from datetime import date, datetime, timedelta, timezone

# Zona del negocio: único lugar donde se define. Guatemala no tiene horario
# de verano (UTC-6 todo el año); un desfase fijo evita depender de la base de
# zonas horarias del sistema o de la variable TZ del contenedor.
ZONA_LOCAL = timezone(timedelta(hours=-6), "America/Guatemala")


def ahora_utc() -> datetime:
    """Momento actual en UTC naive (el mismo formato que created_at). Las
    pruebas lo reemplazan para fijar el reloj."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hoy_local(ahora: datetime | None = None) -> date:
    """Fecha de hoy en Guatemala. `ahora` es UTC naive; por defecto, ahora_utc()."""
    if ahora is None:
        ahora = ahora_utc()
    return ahora.replace(tzinfo=timezone.utc).astimezone(ZONA_LOCAL).date()


def local_day_bounds(fecha: date) -> tuple[datetime, datetime]:
    """Rango [inicio, fin) del día `fecha` en Guatemala, como datetimes
    naive-UTC comparables contra columnas pobladas con datetime.utcnow().
    Ej.: 2026-11-15 -> [2026-11-15 06:00, 2026-11-16 06:00) UTC."""
    inicio_local = datetime(fecha.year, fecha.month, fecha.day, tzinfo=ZONA_LOCAL)
    fin_local = inicio_local + timedelta(days=1)
    return (
        inicio_local.astimezone(timezone.utc).replace(tzinfo=None),
        fin_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def limites_hoy_guatemala(ahora: datetime | None = None) -> tuple[datetime, datetime]:
    """Límites del día de hoy en Guatemala (los de local_day_bounds)."""
    return local_day_bounds(hoy_local(ahora))
