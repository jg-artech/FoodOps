"""Payload JSON de FoodOps -> bytes ESC/POS.

El backend manda datos estructurados, nunca HTML (docs/DISENO_IMPRESION.md
§9.1). Toda la lógica específica de la impresora vive aquí: si cambia el
modelo, solo cambia este archivo.
"""
from datetime import datetime, timezone

ESC = b"\x1b"
GS = b"\x1d"

INICIALIZAR = ESC + b"@"
CODEPAGE_CP850 = ESC + b"t\x02"
ALINEAR_IZQ = ESC + b"a\x00"
ALINEAR_CENTRO = ESC + b"a\x01"
NEGRITA_ON = ESC + b"E\x01"
NEGRITA_OFF = ESC + b"E\x00"
DOBLE_ALTO = GS + b"!\x01"
TAMANO_NORMAL = GS + b"!\x00"
# Avanza y corta parcial (GS V 66 n).
CORTE = GS + b"V\x42\x00"

# Pulso de apertura del cajón: ESC p 0 25 250. Probado físicamente en la
# AON PR-350WF (decisión 9 de §11).
PULSO_CAJON = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])

METODOS = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}


def _limpiar(texto) -> str:
    """Quita caracteres de control: un nombre de cliente o una nota con un
    ESC incrustado no puede inyectar comandos (p. ej. abrir el cajón)."""
    if texto is None:
        return ""
    return "".join(c for c in str(texto) if c >= " " and c != "\x7f")


def _b(texto: str) -> bytes:
    return texto.encode("cp850", errors="replace")


def _linea(texto: str = "") -> bytes:
    return _b(texto) + b"\n"


def _partir(texto: str, ancho: int) -> list[str]:
    texto = _limpiar(texto)
    if not texto:
        return [""]
    return [texto[i:i + ancho] for i in range(0, len(texto), ancho)]


def _fila(izq: str, der: str, ancho: int) -> list[str]:
    """Texto a la izquierda, monto a la derecha; si no cabe, parte en líneas."""
    izq, der = _limpiar(izq), _limpiar(der)
    espacio = ancho - len(der) - 1
    if espacio < 1:
        return _partir(izq, ancho) + [der.rjust(ancho)]
    partes = _partir(izq, espacio)
    partes[-1] = partes[-1].ljust(espacio) + " " + der
    return partes


def _q(valor) -> str:
    try:
        return f"Q{float(valor or 0):.2f}"
    except (TypeError, ValueError):
        return "Q0.00"


def _fecha_local(texto) -> str:
    """created_at viene en UTC naive (datetime.utcnow del backend)."""
    if not texto:
        return ""
    try:
        dt = datetime.fromisoformat(str(texto)).replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return _limpiar(texto)
    return dt.strftime("%d/%m/%Y %H:%M")


def ticket(payload: dict, ancho: int = 42, nombre_negocio: str = "Asados a la Leña") -> bytes:
    """Mismo contenido que foodops-web/src/utils/ticket.js, en ESC/POS."""
    if not isinstance(payload, dict) or not isinstance(payload.get("orden"), dict):
        raise ValueError("Payload de ticket inválido: se esperaba JSON con 'orden'")
    o = payload["orden"]
    sep = _linea("-" * ancho)
    out = [INICIALIZAR, CODEPAGE_CP850]

    out += [ALINEAR_CENTRO, NEGRITA_ON, DOBLE_ALTO]
    out += [_linea(t) for t in _partir(nombre_negocio, ancho)]
    out += [TAMANO_NORMAL]
    if o.get("punto_nombre"):
        out += [_linea(t) for t in _partir(o["punto_nombre"], ancho)]
    out += [NEGRITA_OFF, _linea(_fecha_local(o.get("created_at"))), ALINEAR_IZQ, sep]

    filas = _fila("Orden:", o.get("numero_orden") or "", ancho)
    filas += _fila("Tipo:", "Domicilio" if o.get("es_domicilio") else "Para llevar", ancho)
    if o.get("es_domicilio"):
        filas += _fila("Cliente:", o.get("cliente_nombre") or "", ancho)
        filas += _fila("Tel:", o.get("cliente_telefono") or "", ancho)
        filas += _partir(o.get("cliente_direccion") or "", ancho)
    filas += _fila("Atendió:", o.get("tomada_por_nombre") or "", ancho)
    out += [_linea(t) for t in filas] + [sep]

    for i in o.get("items") or []:
        try:
            subtotal = float(i.get("cantidad") or 0) * float(i.get("precio_unitario") or 0)
        except (TypeError, ValueError):
            subtotal = 0
        out += [_linea(t) for t in _fila(f"{i.get('cantidad')}x {i.get('producto')}",
                                         _q(subtotal), ancho)]
        if i.get("especiales"):
            out += [_linea("  > " + t) for t in _partir(i["especiales"], ancho - 4)]
    out += [sep]

    out += [NEGRITA_ON, DOBLE_ALTO]
    out += [_linea(t) for t in _fila("TOTAL", _q(o.get("total")), ancho)]
    out += [TAMANO_NORMAL, NEGRITA_OFF]
    metodo = o.get("metodo_pago")
    out += [_linea(t) for t in _fila("Pago:", METODOS.get(metodo, metodo or ""), ancho)]
    if metodo == "efectivo":
        # Lo confirmado por el responsable manda sobre el estimado del vendedor.
        recibido = o.get("monto_recibido")
        vuelto = o.get("vuelto_entregado")
        if recibido is None:
            recibido, vuelto = o.get("dinero_recibido"), o.get("vuelto")
        if recibido:
            out += [_linea(t) for t in _fila("Recibido:", _q(recibido), ancho)]
            out += [NEGRITA_ON]
            out += [_linea(t) for t in _fila("Vuelto:", _q(vuelto), ancho)]
            out += [NEGRITA_OFF]
    if o.get("notas_especiales"):
        out += [sep, NEGRITA_ON, _linea("ESPECIALES:"), NEGRITA_OFF]
        out += [_linea(t) for t in _partir(o["notas_especiales"], ancho)]

    out += [sep, ALINEAR_CENTRO, _linea("¡Gracias por su compra!"), ALINEAR_IZQ]
    out += [b"\n\n\n", CORTE]
    return b"".join(out)


def abrir_cajon() -> bytes:
    return INICIALIZAR + PULSO_CAJON
