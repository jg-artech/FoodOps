"""Página de prueba de code page para la impresora térmica (ESC/POS).

Imprime un bloque por cada code page candidata, con la misma línea de
texto, para ver cuál muestra bien los acentos, la eñe y el euro. Lo que
una code page no tiene se imprime como '?'.

Uso, en una CONSOLA (no con pythonw), desde la carpeta tools\\:

    python -m agente_impresion.prueba_impresora --ip <IP_IMPRESORA>
    python -m agente_impresion.prueba_impresora --ip <IP_IMPRESORA> --puerto 9100

O con las mismas variables de entorno del agente:

    set FOODOPS_IMPRESORA_IP=<IP_IMPRESORA>
    python -m agente_impresion.prueba_impresora

Sin imprimir (solo muestra los bytes que enviaría):

    python -m agente_impresion.prueba_impresora --ip <IP_IMPRESORA> --mostrar

No abre el cajón: nunca envía el pulso ESC p.
"""
import argparse
import os
import socket
import sys

ESC = b"\x1b"
GS = b"\x1d"
INICIALIZAR = ESC + b"@"
CORTE = GS + b"V\x42\x00"  # avanza y corta parcial

LINEA_PRUEBA = "Leña Jordán Atendió Porción ¿Sí? ñÑ áéíóú ÁÉÍÓÚ ¡Hola! €"

# (nombre, n de ESC t n, codificación de Python). Números de la tabla ESC t
# estándar de Epson; los clones pueden diferir, por eso se prueban todas.
CANDIDATAS = [
    ("CP850", 2, "cp850"),
    ("CP858", 19, "cp858"),
    ("WPC1252", 16, "cp1252"),
    ("CP437", 0, "cp437"),
]


def bloque(nombre: str, n: int, codificacion: str) -> bytes:
    """ESC t n + encabezado ASCII + línea de prueba en esa codificación."""
    encabezado = f"=== {nombre} (ESC t {n}) ===\n".encode("ascii")
    texto = (LINEA_PRUEBA + "\n\n").encode(codificacion, errors="replace")
    return ESC + b"t" + bytes([n]) + encabezado + texto


def pagina_de_prueba() -> bytes:
    partes = [INICIALIZAR, b"PRUEBA DE CODE PAGE - FoodOps\n\n"]
    partes += [bloque(*c) for c in CANDIDATAS]
    # Deja la impresora como estaba (ESC @ reinicia la code page).
    partes += [INICIALIZAR, b"\n\n\n", CORTE]
    return b"".join(partes)


def enviar(ip: str, puerto: int, datos: bytes, timeout: float = 5.0) -> None:
    with socket.create_connection((ip, puerto), timeout=timeout) as s:
        s.sendall(datos)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Página de prueba de code page ESC/POS.")
    p.add_argument("--ip", default=os.environ.get("FOODOPS_IMPRESORA_IP"),
                   help="IP de la impresora (o FOODOPS_IMPRESORA_IP)")
    p.add_argument("--puerto", type=int,
                   default=int(os.environ.get("FOODOPS_IMPRESORA_PUERTO", 9100)),
                   help="Puerto ESC/POS (o FOODOPS_IMPRESORA_PUERTO; por defecto 9100)")
    p.add_argument("--mostrar", action="store_true",
                   help="No imprime: muestra los bytes que enviaría")
    args = p.parse_args(argv)

    datos = pagina_de_prueba()
    if args.mostrar:
        for nombre, n, cod in CANDIDATAS:
            print(f"{nombre:8} ESC t {n:<2} -> {bloque(nombre, n, cod).hex(' ')}")
        return 0

    if not args.ip:
        print("Falta la IP de la impresora: use --ip o defina FOODOPS_IMPRESORA_IP.",
              file=sys.stderr)
        return 2
    try:
        enviar(args.ip, args.puerto, datos)
    except OSError as e:
        print(f"No se pudo enviar a {args.ip}:{args.puerto}: {e}", file=sys.stderr)
        return 1
    print(f"Página de prueba enviada a {args.ip}:{args.puerto} ({len(datos)} bytes).")
    print("Anote qué bloque muestra bien: Leña Jordán Atendió Porción ¿Sí? ñÑ áéíóú ÁÉÍÓÚ ¡Hola! €")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
