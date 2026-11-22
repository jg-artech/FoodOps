"""Payload JSON de FoodOps -> bytes ESC/POS.

El backend manda datos estructurados, nunca HTML (docs/DISENO_IMPRESION.md
§9.1). Toda la lógica específica de la impresora vive aquí: si cambia el
modelo, solo cambia este archivo.
"""
from datetime import datetime, timezone

ESC = b"\x1b"
GS = b"\x1d"

INICIALIZAR = ESC + b"@"
# FS . cancela el modo chino. La AON PR-350WF de Centro trae "Chinese
# mode: YES" en sus DIP: así lee los bytes > 0x7F como GB2312 e ignora el
# code page, y la ñ y los acentos salen mal. Probado físicamente
# (2026-11-21): con FS . + ESC t 2 (CP850) "Leña áéíóú" sale bien.
CANCELAR_MODO_CHINO = b"\x1c."
# Code page del ticket: CP858 (ESC t 19), que es CP850 con el € en 0xD5.
# Va después de ESC @ (que la restablece) y de FS ., antes del texto.
CODE_PAGE = 19
CODIFICACION = "cp858"
SELECCIONAR_CODE_PAGE = ESC + b"t" + bytes([CODE_PAGE])
ALINEAR_IZQ = ESC + b"a\x00"
ALINEAR_CENTRO = ESC + b"a\x01"
NEGRITA_ON = ESC + b"E\x01"
NEGRITA_OFF = ESC + b"E\x00"
DOBLE_ALTO = GS + b"!\x01"
TAMANO_NORMAL = GS + b"!\x00"
# Fin de ticket: avanza 4 líneas (ESC d 4) para que el texto pase la
# cuchilla y luego corte total (GS V 0). Corte confirmado en la AON
# PR-350WF (2026-11-21, enviando estos bytes con la herramienta de prueba
# del fabricante). Solo para TICKET: el
# trabajo de cajón no avanza ni corta.
ALIMENTAR_ANTES_CORTE = bytes([0x1B, 0x64, 0x04])
CORTE_TOTAL = bytes([0x1D, 0x56, 0x00])

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
    return texto.encode(CODIFICACION, errors="replace")


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
    out = [INICIALIZAR, CANCELAR_MODO_CHINO, SELECCIONAR_CODE_PAGE]

    out += [ALINEAR_CENTRO, NEGRITA_ON, DOBLE_ALTO]
    out += [_linea(t) for t in _partir(nombre_negocio, ancho)]
    out += [TAMANO_NORMAL]
    if o.get("punto_nombre"):
        out += [_linea(t) for t in _partir(o["punto_nombre"], ancho)]
    out += [NEGRITA_OFF, _linea(_fecha_local(o.get("created_at"))), ALINEAR_IZQ, sep]

    out += [_linea(t) for t in _fila("Orden:", o.get("numero_orden") or "", ancho)]
    # El nombre va siempre (también "para llevar"), en negrita y doble alto,
    # justo debajo de la orden: con él se llama al cliente al entregar.
    out += [NEGRITA_ON, DOBLE_ALTO]
    out += [_linea(t) for t in _fila("Cliente:", o.get("cliente_nombre") or "", ancho)]
    out += [TAMANO_NORMAL, NEGRITA_OFF]

    filas = _fila("Tipo:", "Domicilio" if o.get("es_domicilio") else "Para llevar", ancho)
    if o.get("es_domicilio"):
        filas += _fila("Tel:", o.get("cliente_telefono") or "", ancho)
        filas += _partir(o.get("cliente_direccion") or "", ancho)
    filas += _fila("Atendió:", o.get("tomada_por_nombre") or "", ancho)
    out += [_linea(t) for t in filas] + [sep]

    for i in o.get("items") or []:
        try:
            subtotal = float(i.get("cantidad") or 0) * float(i.get("precio_unitario") or 0)
        except (TypeError, ValueError):
            subtotal = 0
        # El cargo de entrega va sin "1x": no es un producto.
        if i.get("tipo") == "entrega":
            etiqueta = str(i.get("producto") or "Cargo de entrega")
        else:
            etiqueta = f"{i.get('cantidad')}x {i.get('producto')}"
        out += [_linea(t) for t in _fila(etiqueta, _q(subtotal), ancho)]
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
    out += [ALIMENTAR_ANTES_CORTE, CORTE_TOTAL]
    return b"".join(out)


def abrir_cajon() -> bytes:
    return INICIALIZAR + PULSO_CAJON
