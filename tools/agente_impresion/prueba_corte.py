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

No abre el cajón: nunca envía el pulso ESC p.
"""
import argparse
import os
import sys
from datetime import datetime

from . import escpos
from .agente import ImpresoraTCP

FIN_ESPERADO = escpos.ALIMENTAR_ANTES_CORTE + escpos.CORTE_TOTAL


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
    a = p.parse_args(argv)

    datos = datos_de_prueba(a.sin_corte)
    print(f"Bytes finales: {datos[-6:].hex(' ').upper()}")
    if not a.sin_corte:
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
