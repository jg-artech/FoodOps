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

// ─── Responsable de cocina ───
import { puedeElegirResponsable, faltaResponsable } from '../src/permisos.js'

const cocinero = { user_id: 30, rol: 'cocinero', punto_id: 8 }
const sinResponsable = { id: 5, estado: 'pendiente', responsable_cocina: null, exige_responsable_cocina: true }
const conResponsable = { id: 6, estado: 'preparando', responsable_cocina: { id: 1, nombre: 'Ana' }, exige_responsable_cocina: true }

test('el cocinero elige responsable solo si la orden no tiene', () => {
  assert.equal(puedeElegirResponsable(cocinero, sinResponsable), true)
  assert.equal(puedeElegirResponsable(cocinero, conResponsable), false)
})

test('gerencia reasigna mientras la orden no esté cerrada', () => {
  for (const rol of ['resp_tienda', 'gerente_punto', 'gerente_general', 'admin']) {
    assert.equal(puedeElegirResponsable({ rol }, conResponsable), true)
    for (const estado of ['listo', 'entregado', 'cancelado']) {
      assert.equal(puedeElegirResponsable({ rol }, { ...conResponsable, estado }), false)
    }
  }
})

test('vendedor y repartidor no eligen responsable', () => {
  for (const rol of ['tomador_orden', 'repartidor']) {
    assert.equal(puedeElegirResponsable({ rol }, sinResponsable), false)
  }
})

test('falta responsable solo en órdenes que lo exigen', () => {
  assert.equal(faltaResponsable(sinResponsable), true)
  assert.equal(faltaResponsable(conResponsable), false)
  assert.equal(faltaResponsable({ ...sinResponsable, exige_responsable_cocina: false }), false)
})
