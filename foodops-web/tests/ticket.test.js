// Ticket del navegador (src/utils/ticket.js). Sin dependencias: node --test.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { altoPaginaMm, buildTicketHtml } from '../src/utils/ticket.js'

const orden = {
  numero_orden: 'ORD-1', cliente_nombre: 'Ana', total: 50, metodo_pago: 'tarjeta',
  items: [{ cantidad: 1, producto: 'Pollo', precio_unitario: 50 }],
}

test('el alto de página sale del contenido más márgenes y holgura', () => {
  assert.equal(altoPaginaMm(96), 36) // 96 px = 25.4 mm -> 26 + 10
  assert.equal(altoPaginaMm(960), 264) // 254 mm + 10
  assert.equal(altoPaginaMm(0), 10)
  assert.equal(altoPaginaMm(undefined), 10)
})

test('el ticket no usa "size: 70mm auto", que Chrome ignora', () => {
  const html = buildTicketHtml(orden)
  assert.doesNotMatch(html, /size:\s*70mm auto/)
  assert.match(html, /@page \{ size: 70mm 200mm;/)
})

test('el ticket fija el alto de página antes de llamar a window.print()', () => {
  const html = buildTicketHtml(orden)
  assert.doesNotMatch(html, /onload="window.print\(\)"/)
  const script = html.slice(html.indexOf('<script>'))
  assert.ok(script.indexOf("@page { size: 70mm '") < script.indexOf('window.print()'))
  assert.match(script, /function altoPaginaMm/)
})

test('al cargar, el script pide una página del alto del contenido y luego imprime', () => {
  const html = buildTicketHtml(orden)
  const js = html.slice(html.indexOf('<script>') + 8, html.indexOf('</script>'))
  const pasos = []
  let onload
  const win = { addEventListener: (_, f) => { onload = f }, print: () => pasos.push('print') }
  const doc = {
    body: { scrollHeight: 700 },
    createElement: () => ({}),
    head: { appendChild: (e) => pasos.push(e.textContent) },
  }
  new Function('window', 'document', js)(win, doc)
  onload()
  assert.deepEqual(pasos, ['@page { size: 70mm 196mm; margin: 3mm 2mm; }', 'print'])
})
