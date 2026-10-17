"""Configuración de pytest.

Apunta toda la suite a una base de datos de prueba independiente
(<bd>_test) ANTES de importar nada de foodops: los routers crean su engine
en tiempo de import a partir de settings, así que la variable de entorno
tiene que estar puesta primero. La BD de desarrollo no se toca.
"""

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

load_dotenv()

_url_dev = make_url(os.environ["DATABASE_SYNC_URL"])
_nombre_test = f"{_url_dev.database}_test"
_url_test = _url_dev.set(database=_nombre_test)

os.environ["DATABASE_SYNC_URL"] = _url_test.render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = _url_test.set(
    drivername="postgresql+asyncpg"
).render_as_string(hide_password=False)


def _crear_bd_de_prueba() -> None:
    admin = create_engine(
        _url_dev.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": _nombre_test}
            ).first()
            if not existe:
                conn.execute(text(f'CREATE DATABASE "{_nombre_test}"'))
    finally:
        admin.dispose()


_crear_bd_de_prueba()

# A partir de aquí ya es seguro importar la app: el engine apuntará a la BD
# de prueba.
from foodops.db.models import Base  # noqa: E402
import foodops.db.models_caja  # noqa: E402,F401  - registra tablas en Base.metadata
import foodops.db.models_stock  # noqa: E402,F401
from foodops.main import app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(os.environ["DATABASE_SYNC_URL"])
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def api():
    from fastapi.testclient import TestClient

    with TestClient(app) as cliente:
        yield cliente
