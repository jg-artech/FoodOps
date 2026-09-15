// Generación e impresión de tickets de orden (impresora térmica angosta,
// máx. 7cm de ancho). Se usa tanto al confirmar una orden nueva
// (NewOrderView) como para reimprimir una orden ya existente (OrdenList).
// Recibe el objeto "orden" tal como lo devuelve GET/POST /api/ordenes/
// (numero_orden, total, cliente_*, metodo_pago, dinero_recibido, vuelto,
// created_at, tomada_por_nombre, notas_especiales, items[]).

const METODOS_LABEL = {
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
  transferencia: 'Transferencia',
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]))
}

function formatFechaTicket(str) {
  if (!str) return ''
  // El backend guarda en UTC sin 'Z' — agregamos 'Z' para parsear correctamente
  const d = new Date(str.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return str
  return d.toLocaleString('es-GT', { dateStyle: 'short', timeStyle: 'short' })
}

function buildTicketHtml(orden) {
  const nombreNegocio = 'Asados a la Leña'
  const nombrePlataforma = import.meta.env.VITE_APP_NAME || 'FoodOps'
  const metodoLabel = METODOS_LABEL[orden?.metodo_pago] || orden?.metodo_pago || ''

  const filasItems = (orden?.items || []).map((i) => `
    <div class="row">
      <span class="item-name">${escapeHtml(i.cantidad)}x ${escapeHtml(i.producto)}</span>
      <span class="item-price">Q${(i.cantidad * i.precio_unitario).toFixed(2)}</span>
    </div>
    ${i.especiales ? `<div class="muted item-especiales">↳ ${escapeHtml(i.especiales)}</div>` : ''}`).join('')

  const bloqueCliente = orden?.es_domicilio ? `
    <div class="row"><span>Cliente:</span><span>${escapeHtml(orden.cliente_nombre)}</span></div>
    <div class="row"><span>Tel:</span><span>${escapeHtml(orden.cliente_telefono)}</span></div>
    <div class="muted">${escapeHtml(orden.cliente_direccion)}</div>` : ''

  const bloqueEfectivo = orden?.metodo_pago === 'efectivo' && orden?.dinero_recibido ? `
    <div class="row"><span>Recibido:</span><span>Q${Number(orden.dinero_recibido).toFixed(2)}</span></div>
    <div class="row bold"><span>Vuelto:</span><span>Q${Number(orden.vuelto || 0).toFixed(2)}</span></div>` : ''

  const bloqueNotas = orden?.notas_especiales ? `
    <hr>
    <div class="bold">⚠ ESPECIALES:</div>
    <div>${escapeHtml(orden.notas_especiales)}</div>` : ''

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Ticket ${escapeHtml(orden?.numero_orden)}</title>
<style>
  @page { size: 70mm auto; margin: 3mm 2mm; }
  * { box-sizing: border-box; }
  body {
    width: 70mm;
    margin: 0;
    font-family: 'Courier New', Courier, monospace;
    font-size: 11px;
    line-height: 1.35;
    color: #000;
  }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .big { font-size: 15px; }
  .muted { font-size: 10px; color: #333; }
  .row { display: flex; justify-content: space-between; gap: 6px; }
  .item-name { flex: 1; padding-right: 4px; word-break: break-word; }
  .item-price { white-space: nowrap; }
  .item-especiales { padding-left: 8px; margin: -2px 0 4px; }
  hr { border: none; border-top: 1px dashed #000; margin: 6px 0; }
</style>
</head>
<body onload="window.print()">
  <div class="center bold big">${escapeHtml(nombreNegocio)}</div>
  <div class="center muted">${escapeHtml(nombrePlataforma)}</div>
  <div class="center muted">${formatFechaTicket(orden?.created_at)}</div>
  <hr>
  <div class="row"><span>Orden:</span><span class="bold">${escapeHtml(orden?.numero_orden)}</span></div>
  <div class="row"><span>Tipo:</span><span>${orden?.es_domicilio ? 'Domicilio' : 'Para llevar'}</span></div>
  ${bloqueCliente}
  <div class="row"><span>Atendió:</span><span>${escapeHtml(orden?.tomada_por_nombre || '')}</span></div>
  <hr>
  ${filasItems}
  <hr>
  <div class="row bold big"><span>TOTAL</span><span>Q${Number(orden?.total || 0).toFixed(2)}</span></div>
  <div class="row"><span>Pago:</span><span>${escapeHtml(metodoLabel)}</span></div>
  ${bloqueEfectivo}
  ${bloqueNotas}
  <hr>
  <div class="center muted">¡Gracias por su compra!</div>
</body>
</html>`
}

// Abre una ventana nueva con SOLO el HTML del ticket (sin navbar ni resto de
// la app), con su propio @page a 70mm de ancho, e imprime desde ahí. Funciona
// con cualquier impresora (térmica o normal) configurada en el navegador.
export function imprimirTicket(orden) {
  const win = window.open('', '_blank', 'width=380,height=600')
  if (!win) {
    alert('El navegador bloqueó la ventana de impresión. Habilita las ventanas emergentes para este sitio.')
    return
  }
  win.document.open()
  win.document.write(buildTicketHtml(orden))
  win.document.close()
}
