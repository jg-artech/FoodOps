#!/usr/bin/env python3
"""Crea uno o varios usuarios en la BD apuntada por DATABASE_SYNC_URL (.env).

No existe endpoint ni pantalla para esto todavía (ver
docs/AUDITORIA_MULTITIENDA.md) - es la única vía mientras tanto. Reutiliza
hash_password() de foodops.core.auth para generar el mismo hash bcrypt que
el login verifica, evitando tener que hashear a mano con SQL.

Uso - un usuario por línea de comandos:
    PYTHONPATH=src python3 scripts/crear_usuario.py \
        --username vendedor_jordan --email vendedor.jordan@foodops.gt \
        --password "Cambiar123!" --rol tomador_orden --punto "Local Jordán" \
        --nombre "Vendedor Jordán"

    # Sin --punto: válido solo para ADMIN, GERENTE_GENERAL o GERENTE_CENTRAL
    # (el CHECK de la migración 010 rechaza cualquier otro rol sin tienda).
    PYTHONPATH=src python3 scripts/crear_usuario.py \
        --username gerente_regional --email gg2@foodops.gt \
        --password "Cambiar123!" --rol gerente_general

Uso - varios de una vez, desde una plantilla CSV (ver
scripts/usuarios_template.csv):
    PYTHONPATH=src python3 scripts/crear_usuario.py --csv mis_usuarios.csv

    Columnas: username,email,password,rol,punto,nombre_completo
    - punto puede ir vacío solo para los roles multitienda.
    - Una fila que falla (usuario duplicado, tienda inválida, etc.) se
      reporta y se salta; el resto del archivo se procesa igual.

Para ver qué tiendas y roles existen sin crear nada:
    PYTHONPATH=src python3 scripts/crear_usuario.py --listar

Nota de seguridad: --password (o la columna password del CSV) viaja en
texto plano. En un servidor compartido, preferir --password-env para el
modo de un solo usuario (lee la contraseña de una variable de entorno, que
no queda en el historial de shell ni en `ps`); para el CSV, borrar el
archivo (o al menos la columna password) después de usarlo.
"""
import argparse
import csv
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as SessionType, sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from foodops.core.auth import hash_password  # noqa: E402
from foodops.core.config import settings  # noqa: E402
from foodops.db.models import PuntoVenta, Usuario, UserRol  # noqa: E402

# Roles que, por el CHECK ck_usuarios_tienda_segun_rol (migración 010),
# pueden existir sin punto_id.
_ROLES_SIN_TIENDA = {"ADMIN", "GERENTE_GENERAL", "GERENTE_CENTRAL"}


def _listar(session: SessionType) -> None:
    print("Tiendas:")
    for p in session.execute(select(PuntoVenta).order_by(PuntoVenta.id)).scalars():
        print(f"  id={p.id:<4} {p.nombre}")
    print("\nRoles válidos:")
    for r in UserRol:
        libre = " (puede ir sin tienda)" if r.name in _ROLES_SIN_TIENDA else ""
        print(f"  {r.value}{libre}")


def _resolver_punto(session: SessionType, valor: str) -> PuntoVenta:
    """Acepta un id numérico o el nombre (coincidencia parcial, case-insensitive)."""
    if valor.isdigit():
        punto = session.get(PuntoVenta, int(valor))
        if punto:
            return punto
        raise ValueError(f"No existe ningún punto de venta con id={valor}")
    candidatos = [
        p
        for p in session.execute(select(PuntoVenta)).scalars()
        if valor.lower() in p.nombre.lower()
    ]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise ValueError(f"Ningún punto de venta coincide con '{valor}'. Usa --listar para ver los nombres.")
    nombres = ", ".join(p.nombre for p in candidatos)
    raise ValueError(f"'{valor}' coincide con varias tiendas ({nombres}); sé más específico o usa el id.")


def _empresa_por_defecto(session: SessionType) -> int:
    empresas = session.execute(select(Usuario.empresa_id).distinct()).scalars().all()
    if len(empresas) == 1:
        return empresas[0]
    raise ValueError(f"Hay varias empresas ({empresas}); pasa empresa_id explícitamente.")


def crear_uno(
    session: SessionType,
    *,
    username: str,
    email: str,
    password: str,
    rol_valor: str,
    punto_valor: str | None = None,
    nombre: str | None = None,
    empresa_id: int | None = None,
) -> Usuario:
    """Valida y crea un usuario. No hace commit (el caller decide cuándo),
    para que el modo CSV pueda confirmar fila por fila sin perder las
    anteriores si una falla. Lanza ValueError con el motivo si algo no
    cuadra - nunca SystemExit, para que el modo CSV pueda capturarlo y
    seguir con la siguiente fila."""
    if not username or not email or not rol_valor:
        raise ValueError("username, email y rol son obligatorios")
    if not password:
        raise ValueError("falta la contraseña")

    rol_valores = {r.value: r for r in UserRol}
    if rol_valor not in rol_valores:
        raise ValueError(f"rol inválido: '{rol_valor}'. Válidos: {', '.join(rol_valores)}")
    rol = rol_valores[rol_valor]

    punto = None
    if punto_valor:
        punto = _resolver_punto(session, punto_valor)
    elif rol.name not in _ROLES_SIN_TIENDA:
        raise ValueError(
            f"el rol '{rol_valor}' necesita una tienda (no está en la lista de roles multitienda: "
            f"{', '.join(r.lower() for r in _ROLES_SIN_TIENDA)})"
        )

    if session.execute(select(Usuario).where(Usuario.username == username)).scalars().first():
        raise ValueError(f"ya existe un usuario con username '{username}'")
    if session.execute(select(Usuario).where(Usuario.email == email)).scalars().first():
        raise ValueError(f"ya existe un usuario con email '{email}'")

    if empresa_id is None:
        empresa_id = _empresa_por_defecto(session)

    usuario = Usuario(
        empresa_id=empresa_id,
        punto_id=punto.id if punto else None,
        username=username,
        email=email,
        password_hash=hash_password(password),
        nombre_completo=nombre or username,
        rol=rol,
        activo=True,
    )
    session.add(usuario)
    session.flush()  # asigna el id sin confirmar la transacción todavía
    return usuario


def _crear_desde_csv(session: SessionType, ruta: str) -> None:
    creados, fallidos = 0, 0
    with open(ruta, newline="", encoding="utf-8") as f:
        lector = csv.DictReader(f)
        columnas_esperadas = {"username", "email", "password", "rol"}
        if not columnas_esperadas.issubset(lector.fieldnames or []):
            raise SystemExit(
                f"El CSV necesita al menos las columnas {sorted(columnas_esperadas)}; "
                f"tiene {lector.fieldnames}. Ver scripts/usuarios_template.csv."
            )
        for i, fila in enumerate(lector, start=2):  # fila 1 = encabezado
            username = (fila.get("username") or "").strip()
            try:
                usuario = crear_uno(
                    session,
                    username=username,
                    email=(fila.get("email") or "").strip(),
                    password=(fila.get("password") or "").strip(),
                    rol_valor=(fila.get("rol") or "").strip(),
                    punto_valor=(fila.get("punto") or "").strip() or None,
                    nombre=(fila.get("nombre_completo") or "").strip() or None,
                )
                session.commit()
                print(f"  fila {i}: OK  id={usuario.id} username={usuario.username} rol={usuario.rol.value}")
                creados += 1
            except ValueError as e:
                session.rollback()
                print(f"  fila {i}: ERROR ({username or '(sin username)'}): {e}")
                fallidos += 1
    print(f"\nTotal: {creados} creados, {fallidos} con error.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--listar", action="store_true", help="Muestra tiendas y roles válidos, no crea nada.")
    parser.add_argument("--csv", help="Ruta a un CSV de usuarios (ver scripts/usuarios_template.csv).")
    parser.add_argument("--username")
    parser.add_argument("--email")
    parser.add_argument("--password", help="Contraseña en texto plano (ver nota de seguridad arriba).")
    parser.add_argument("--password-env", help="Nombre de una variable de entorno con la contraseña.")
    parser.add_argument("--rol", help="Uno de los valores listados con --listar, ej. tomador_orden.")
    parser.add_argument("--punto", help="Nombre (parcial) o id de la tienda. Omitir solo para roles multitienda.")
    parser.add_argument("--nombre", default=None, help="Nombre completo para mostrar en la UI.")
    parser.add_argument("--empresa-id", type=int, default=None, help="Por defecto, la única empresa existente.")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_SYNC_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if args.listar:
            _listar(session)
            return

        if args.csv:
            _crear_desde_csv(session, args.csv)
            return

        faltantes = [n for n, v in [("--username", args.username), ("--email", args.email), ("--rol", args.rol)] if not v]
        if faltantes:
            raise SystemExit(f"Faltan argumentos obligatorios: {', '.join(faltantes)} (o usa --listar / --csv).")

        password = args.password or (os.environ.get(args.password_env) if args.password_env else None)
        if not password:
            raise SystemExit("Pasa --password o --password-env con una variable que contenga la contraseña.")

        try:
            usuario = crear_uno(
                session,
                username=args.username,
                email=args.email,
                password=password,
                rol_valor=args.rol,
                punto_valor=args.punto,
                nombre=args.nombre,
                empresa_id=args.empresa_id,
            )
        except ValueError as e:
            raise SystemExit(str(e))

        session.commit()
        punto_nombre = usuario.punto.nombre if usuario.punto_id else "(todas / ninguna en concreto)"
        print(f"Usuario creado: id={usuario.id} username={usuario.username} rol={usuario.rol.value} "
              f"tienda={punto_nombre}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
