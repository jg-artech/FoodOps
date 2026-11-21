"""Ticket de prueba para comprobar físicamente el corte de papel.

Arma el ticket con la misma función que usa el agente (escpos.ticket) y lo
envía con la misma clase (agente.ImpresoraTCP). No usa backend, token ni
base de datos. El ticket termina con avance de 4 líneas (ESC d 4) y corte
total (GS V 0).

Uso, en una CONSOLA, desde la carpeta tools\\:

    python -m agente_impresion.prueba_corte --ip <IP_IMPRESORA> --mostrar
    python -m agente_impresion.prueba_corte --ip <IP_IMPRESORA>
    python -m agente_impresion.prueba_corte --ip <IP_IMPRESORA> --sin-corte

--mostrar no imprime: muestra los bytes finales que enviaría.
--sin-corte imprime el mismo ticket sin avance ni corte, como control: si
ese sale pegado al rollo y el normal sale cortado, el corte lo hace el
comando del ticket.

Si el ticket no corta, pruebe los comandos de corte uno por uno:

    python -m agente_impresion.prueba_corte --variantes
    python -m agente_impresion.prueba_corte --ip <IP_IMPRESORA> --variante A

Cada variante imprime unas líneas con su letra y el comando, y luego el
comando de corte. Anote cuál corta y cuánto papel avanza.

No abre el cajón: nunca envía el pulso ESC p.
"""
import argparse
import os
import sys
from datetime import datetime

from . import escpos
from .agente import ImpresoraTCP

FIN_ESPERADO = escpos.ALIMENTAR_ANTES_CORTE + escpos.CORTE_TOTAL

AVANCE_4 = bytes([0x1B, 0x64, 0x04])  # ESC d 4
# Letra -> (descripción, bytes del final). Las de GS V 65/66 avanzan solas
# hasta la cuchilla; a las demás se les antepone ESC d 4.
VARIANTES = {
    "A": ("ESC d 4 + GS V 0 (corte total, actual)", AVANCE_4 + bytes([0x1D, 0x56, 0x00])),
    "B": ("ESC d 4 + GS V 1 (corte parcial)", AVANCE_4 + bytes([0x1D, 0x56, 0x01])),
    "C": ("ESC d 4 + GS V 48 (corte total, '0' ASCII)", AVANCE_4 + bytes([0x1D, 0x56, 0x30])),
    "D": ("ESC d 4 + GS V 49 (corte parcial, '1' ASCII)", AVANCE_4 + bytes([0x1D, 0x56, 0x31])),
    "E": ("GS V 65 0 (avanza a cuchilla + corte total)", bytes([0x1D, 0x56, 0x41, 0x00])),
    "F": ("GS V 66 0 (avanza a cuchilla + corte parcial)", bytes([0x1D, 0x56, 0x42, 0x00])),
    "G": ("ESC d 4 + ESC i (corte total, antiguo)", AVANCE_4 + bytes([0x1B, 0x69])),
    "H": ("ESC d 4 + ESC m (corte parcial, antiguo)", AVANCE_4 + bytes([0x1B, 0x6D])),
}


def datos_variante(letra: str) -> bytes:
    desc, fin = VARIANTES[letra]
    cuerpo = (
        f"=== VARIANTE {letra} ===\n{desc}\nBytes: {fin.hex(' ').upper()}\n"
        "Linea 1\nLinea 2\nLinea 3 (debe quedar arriba del corte)\n"
    ).encode("ascii")
    return escpos.INICIALIZAR + cuerpo + fin


def payload_de_prueba() -> dict:
    return {
        "orden": {
            "numero_orden": "PRUEBA-CORTE",
            "punto_nombre": "Prueba de corte",
            "created_at": datetime.utcnow().isoformat(),
            "cliente_nombre": "Prueba de corte",
            "es_domicilio": False,
            "tomada_por_nombre": "Prueba",
            "items": [{"cantidad": 1, "producto": "Ticket de prueba", "precio_unitario": 0}],
            "total": 0,
            "metodo_pago": "tarjeta",
        }
    }


def datos_de_prueba(sin_corte: bool = False) -> bytes:
    datos = escpos.ticket(payload_de_prueba())
    if sin_corte:
        assert datos.endswith(FIN_ESPERADO)
        datos = datos[: -len(FIN_ESPERADO)]
    return datos


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ticket de prueba para comprobar el corte de papel.")
    p.add_argument("--ip", default=os.environ.get("FOODOPS_IMPRESORA_IP"),
                   help="IP de la impresora (default: FOODOPS_IMPRESORA_IP)")
    p.add_argument("--puerto", type=int,
                   default=int(os.environ.get("FOODOPS_IMPRESORA_PUERTO", "9100")))
    p.add_argument("--mostrar", action="store_true", help="No imprime: muestra los bytes finales")
    p.add_argument("--sin-corte", action="store_true",
                   help="Control: el mismo ticket sin avance ni corte")
    p.add_argument("--variante", type=str.upper, choices=sorted(VARIANTES),
                   help="Imprime solo esa variante de comando de corte")
    p.add_argument("--variantes", action="store_true", help="Lista las variantes y sale")
    a = p.parse_args(argv)

    if a.variantes:
        for letra, (desc, fin) in VARIANTES.items():
            print(f"{letra}: {desc}  [{fin.hex(' ').upper()}]")
        return 0
    if a.variante:
        datos = datos_variante(a.variante)
    else:
        datos = datos_de_prueba(a.sin_corte)
    print(f"Bytes finales: {datos[-6:].hex(' ').upper()}")
    if not a.sin_corte and not a.variante:
        print(f"Esperado:      {FIN_ESPERADO.hex(' ').upper()} (ESC d 4 + GS V 0)")
    if a.mostrar:
        return 0
    if not a.ip:
        print("Falta la IP: use --ip o FOODOPS_IMPRESORA_IP", file=sys.stderr)
        return 2
    ImpresoraTCP(a.ip, a.puerto, timeout=5).enviar(datos)
    print(f"Enviados {len(datos)} bytes a {a.ip}:{a.puerto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
