#!/usr/bin/env python3
"""Crea un usuario en la BD apuntada por DATABASE_SYNC_URL (.env).

No existe endpoint ni pantalla para esto todavía (ver
docs/AUDITORIA_MULTITIENDA.md) - es la única vía mientras tanto. Reutiliza
hash_password() de foodops.core.auth para generar el mismo hash bcrypt que
el login verifica, evitando tener que hashear a mano con SQL.

Uso:
    PYTHONPATH=src python3 scripts/crear_usuario.py \
        --username vendedor_jordan --email vendedor.jordan@foodops.gt \
        --password "Cambiar123!" --rol tomador_orden --punto "Local Jordán" \
        --nombre "Vendedor Jordán"

    # Sin --punto: válido solo para ADMIN, GERENTE_GENERAL o GERENTE_CENTRAL
    # (el CHECK de la migración 010 rechaza cualquier otro rol sin tienda).
    PYTHONPATH=src python3 scripts/crear_usuario.py \
        --username gerente_regional --email gg2@foodops.gt \
        --password "Cambiar123!" --rol gerente_general

    # Para ver qué tiendas y roles existen sin crear nada:
    PYTHONPATH=src python3 scripts/crear_usuario.py --listar

Nota: --password se pasa en texto plano por la línea de comandos. En un
servidor compartido, preferir --password-env (lee la contraseña de una
variable de entorno, que no queda en el historial de shell ni en `ps`).
"""
import argparse
import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from foodops.core.auth import hash_password  # noqa: E402
from foodops.core.config import settings  # noqa: E402
from foodops.db.models import PuntoVenta, Usuario, UserRol  # noqa: E402

# Roles que, por el CHECK ck_usuarios_tienda_segun_rol (migración 010),
# pueden existir sin punto_id.
_ROLES_SIN_TIENDA = {"ADMIN", "GERENTE_GENERAL", "GERENTE_CENTRAL"}


def _listar(session) -> None:
    print("Tiendas:")
    for p in session.execute(select(PuntoVenta).order_by(PuntoVenta.id)).scalars():
        print(f"  id={p.id:<4} {p.nombre}")
    print("\nRoles válidos:")
    for r in UserRol:
        libre = " (puede ir sin tienda)" if r.name in _ROLES_SIN_TIENDA else ""
        print(f"  {r.value}{libre}")


def _resolver_punto(session, valor: str) -> PuntoVenta:
    """Acepta un id numérico o el nombre (coincidencia parcial, case-insensitive)."""
    if valor.isdigit():
        punto = session.get(PuntoVenta, int(valor))
        if punto:
            return punto
        raise SystemExit(f"No existe ningún punto de venta con id={valor}")
    candidatos = [
        p
        for p in session.execute(select(PuntoVenta)).scalars()
        if valor.lower() in p.nombre.lower()
    ]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise SystemExit(f"Ningún punto de venta coincide con '{valor}'. Usa --listar para ver los nombres.")
    nombres = ", ".join(p.nombre for p in candidatos)
    raise SystemExit(f"'{valor}' coincide con varias tiendas ({nombres}); sé más específico o usa el id.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--listar", action="store_true", help="Muestra tiendas y roles válidos, no crea nada.")
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

        faltantes = [n for n, v in [("--username", args.username), ("--email", args.email), ("--rol", args.rol)] if not v]
        if faltantes:
            raise SystemExit(f"Faltan argumentos obligatorios: {', '.join(faltantes)} (o usa --listar).")

        password = args.password or (os.environ.get(args.password_env) if args.password_env else None)
        if not password:
            raise SystemExit("Pasa --password o --password-env con una variable que contenga la contraseña.")

        rol_valores = {r.value: r for r in UserRol}
        if args.rol not in rol_valores:
            raise SystemExit(f"Rol inválido: '{args.rol}'. Válidos: {', '.join(rol_valores)}")
        rol = rol_valores[args.rol]

        punto = None
        if args.punto:
            punto = _resolver_punto(session, args.punto)
        elif rol.name not in _ROLES_SIN_TIENDA:
            raise SystemExit(
                f"El rol '{args.rol}' necesita --punto (no está en la lista de roles multitienda: "
                f"{', '.join(r.lower() for r in _ROLES_SIN_TIENDA)})."
            )

        if session.execute(select(Usuario).where(Usuario.username == args.username)).scalars().first():
            raise SystemExit(f"Ya existe un usuario con username '{args.username}'.")
        if session.execute(select(Usuario).where(Usuario.email == args.email)).scalars().first():
            raise SystemExit(f"Ya existe un usuario con email '{args.email}'.")

        empresa_id = args.empresa_id
        if empresa_id is None:
            empresas = session.execute(select(Usuario.empresa_id).distinct()).scalars().all()
            if len(empresas) == 1:
                empresa_id = empresas[0]
            else:
                raise SystemExit(f"Hay varias empresas ({empresas}); pasa --empresa-id explícitamente.")

        usuario = Usuario(
            empresa_id=empresa_id,
            punto_id=punto.id if punto else None,
            username=args.username,
            email=args.email,
            password_hash=hash_password(password),
            nombre_completo=args.nombre or args.username,
            rol=rol,
            activo=True,
        )
        session.add(usuario)
        session.commit()

        print(f"Usuario creado: id={usuario.id} username={usuario.username} rol={rol.value} "
              f"tienda={punto.nombre if punto else '(todas / ninguna en concreto)'}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
