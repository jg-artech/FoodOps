// Reglas de botones por rol (src/permisos.js). Sin dependencias: node --test.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { puedeReimprimir } from '../src/permisos.js'

const vendedor = { user_id: 10, rol: 'tomador_orden', punto_id: 8 }
const otroVendedor = { user_id: 11, rol: 'tomador_orden', punto_id: 8 }
const responsable = { user_id: 20, rol: 'resp_tienda', punto_id: 8 }

const propia = { id: 1, tomada_por: 10, punto_id: 8 }
const ajena = { id: 2, tomada_por: 11, punto_id: 8 }
const sinVendedor = { id: 3, tomada_por: null, punto_id: 8 }

test('el vendedor ve el botón de reimprimir en su propia orden', () => {
  assert.equal(puedeReimprimir(vendedor, propia), true)
})

test('el vendedor no ve el botón en la orden de otro vendedor', () => {
  assert.equal(puedeReimprimir(vendedor, ajena), false)
  assert.equal(puedeReimprimir(otroVendedor, propia), false)
})

test('el vendedor no ve el botón en órdenes sin vendedor', () => {
  assert.equal(puedeReimprimir(vendedor, sinVendedor), false)
})

test('el responsable ve el botón en cualquier orden de su tienda', () => {
  for (const orden of [propia, ajena, sinVendedor]) {
    assert.equal(puedeReimprimir(responsable, orden), true)
  }
})

test('los demás roles no se restringen por quién tomó la orden', () => {
  for (const rol of ['gerente_punto', 'gerente_general', 'admin', 'cocinero', 'repartidor']) {
    assert.equal(puedeReimprimir({ user_id: 99, rol }, ajena), true)
  }
})

test('sin sesión no hay botón', () => {
  assert.equal(puedeReimprimir(null, propia), false)
})
