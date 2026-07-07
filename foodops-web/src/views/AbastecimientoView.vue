<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-gray-800">Abastecimiento</h1>
      <RouterLink to="/caja/stock" class="text-sm text-gray-500 hover:text-gray-700">← Stock</RouterLink>
    </div>

    <!-- Selector de responsable -->
    <div class="flex gap-2 mb-4">
      <button v-for="r in responsables" :key="r.value" @click="responsableTipo = r.value; cargarSugerencias()"
        class="flex-1 px-3 py-3 rounded-xl text-sm font-semibold border-2 transition-all"
        :class="responsableTipo === r.value ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-500'">
        {{ r.emoji }} {{ r.label }}
      </button>
    </div>

    <div v-if="sugerencias" class="text-xs text-gray-400 mb-4">
      {{ fechaLabel }} · factor del día: <span class="font-bold text-gray-600">{{ sugerencias.factor_dia }}x</span>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Calculando sugerencias...</div>

    <div v-else-if="pedidoCreado" class="bg-green-50 border border-green-200 rounded-2xl p-5 mb-4 text-center">
      <p class="text-3xl mb-2">✅</p>
      <p class="font-bold text-green-800 mb-1">Pedido(s) creado(s): #{{ pedidoCreado.pedido_ids.join(', #') }}</p>
      <p class="text-sm text-green-600 mb-4">Estado: confirmado</p>
      <div class="flex gap-2 justify-center flex-wrap">
        <button v-for="id in pedidoCreado.pedido_ids" :key="id" @click="enviarPedido(id)"
          :disabled="enviando[id]"
          class="bg-orange-500 hover:bg-orange-600 text-white font-semibold px-4 py-2 rounded-lg text-sm disabled:opacity-40">
          {{ enviados[id] ? '✓ Enviado' : (enviando[id] ? 'Enviando...' : `Marcar #${id} como enviado`) }}
        </button>
      </div>
      <button @click="reiniciar" class="mt-4 text-sm text-gray-500 hover:text-gray-700 underline">
        Generar otra sugerencia
      </button>
    </div>

    <div v-else-if="!sugerencias || sugerencias.puntos.length === 0" class="text-center py-12 text-gray-400">
      <p class="text-4xl mb-3">📦</p>
      <p>Sin sugerencias para {{ responsableLabelActual }} hoy.</p>
      <p class="text-xs mt-1">(sin venta registrada ayer, o sin regla min/máx configurada)</p>
    </div>

    <div v-else class="space-y-4">
      <div v-for="punto in sugerencias.puntos" :key="punto.punto_id" class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <h3 class="font-bold text-gray-700">{{ punto.punto_nombre }}</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-gray-400 text-xs uppercase">
              <tr>
                <th class="text-left px-3 py-2">Item</th>
                <th class="text-right px-3 py-2">Stock</th>
                <th class="text-right px-3 py-2">Consumo ayer</th>
                <th class="text-right px-3 py-2">Sugerido</th>
                <th class="text-right px-3 py-2 w-24">Final</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in punto.items" :key="it.item_id" class="border-t border-gray-100">
                <td class="px-3 py-2">
                  <span class="inline-block w-2 h-2 rounded-full mr-1.5" :class="colorUrgencia(it.urgencia)" :title="it.urgencia" />
                  {{ it.item_nombre }}
                </td>
                <td class="px-3 py-2 text-right text-gray-500">{{ it.stock_actual }}</td>
                <td class="px-3 py-2 text-right text-gray-500">{{ it.consumo_ayer }}</td>
                <td class="px-3 py-2 text-right text-gray-400">{{ it.cantidad_sugerida }}</td>
                <td class="px-3 py-2 text-right">
                  <input type="number" min="0" step="0.01"
                    v-model.number="cantidadesFinales[claveItem(punto.punto_id, it.item_id)]"
                    class="w-20 border border-gray-200 rounded-lg px-2 py-1 text-right text-sm font-semibold text-orange-600 focus:outline-none focus:ring-1 focus:ring-orange-400" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-400">Total sugerido: {{ totalSugerido.toFixed(2) }}</p>
          <p class="font-bold text-gray-800">Total final: <span class="text-orange-500">{{ totalFinal.toFixed(2) }}</span></p>
        </div>
        <button @click="limpiarFinal" class="text-xs text-gray-400 hover:text-gray-600 underline">Restablecer sugeridos</button>
      </div>

      <p v-if="errorMsg" class="text-red-500 text-sm text-center">{{ errorMsg }}</p>
      <button @click="generarPedido" :disabled="!totalFinal || generando"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition disabled:opacity-40">
        {{ generando ? 'Generando...' : '📦 Generar pedido de envío' }}
      </button>

      <RouterLink to="/caja/pedidos-reabastecimiento" class="block text-center border border-gray-300 text-gray-600 font-semibold py-3 rounded-xl hover:bg-gray-50">
        📋 Ver pedidos de reabastecimiento
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const responsables = [
  { value: 'POLLO', label: 'Pollo', emoji: '🍗' },
  { value: 'VEGETAL', label: 'Vegetal', emoji: '🥔' },
  { value: 'DESECHABLE_SALSA', label: 'Desechable/Salsa', emoji: '🧴' },
]

const responsableTipo = ref('POLLO')
const responsableLabelActual = computed(() => responsables.find((r) => r.value === responsableTipo.value)?.label)

const sugerencias = ref(null)
const cantidadesFinales = reactive({})
const loading = ref(true)
const generando = ref(false)
const errorMsg = ref('')
const pedidoCreado = ref(null)
const enviando = reactive({})
const enviados = reactive({})

const fechaLabel = computed(() => sugerencias.value ? `Sugerencias para ${sugerencias.value.fecha}` : '')

function claveItem(puntoId, itemId) {
  return `${puntoId}-${itemId}`
}

function colorUrgencia(u) {
  return { URGENTE: 'bg-red-500', NORMAL: 'bg-yellow-400', OK: 'bg-green-500' }[u] || 'bg-gray-300'
}

async function cargarSugerencias() {
  loading.value = true
  errorMsg.value = ''
  pedidoCreado.value = null
  Object.keys(cantidadesFinales).forEach((k) => delete cantidadesFinales[k])
  try {
    const { data } = await api.get('/api/abastecimiento/sugerencias', { params: { responsable_tipo: responsableTipo.value } })
    sugerencias.value = data
    for (const punto of data.puntos) {
      for (const it of punto.items) {
        cantidadesFinales[claveItem(punto.punto_id, it.item_id)] = it.cantidad_sugerida
      }
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar sugerencias'
    sugerencias.value = null
  } finally {
    loading.value = false
  }
}

function limpiarFinal() {
  if (!sugerencias.value) return
  for (const punto of sugerencias.value.puntos) {
    for (const it of punto.items) {
      cantidadesFinales[claveItem(punto.punto_id, it.item_id)] = it.cantidad_sugerida
    }
  }
}

const totalSugerido = computed(() => {
  if (!sugerencias.value) return 0
  return sugerencias.value.puntos.reduce((s, p) => s + p.items.reduce((s2, it) => s2 + it.cantidad_sugerida, 0), 0)
})

const totalFinal = computed(() =>
  Object.values(cantidadesFinales).reduce((s, v) => s + (Number(v) || 0), 0)
)

async function generarPedido() {
  errorMsg.value = ''
  generando.value = true
  try {
    const items = []
    for (const punto of sugerencias.value.puntos) {
      for (const it of punto.items) {
        const cantidad = Number(cantidadesFinales[claveItem(punto.punto_id, it.item_id)])
        if (cantidad > 0) {
          items.push({ punto_venta_id: punto.punto_id, item_id: it.item_id, cantidad_final: cantidad })
        }
      }
    }
    const { data } = await api.post('/api/abastecimiento/pedido/crear', {
      responsable_tipo: responsableTipo.value,
      items,
    })
    pedidoCreado.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al generar el pedido'
  } finally {
    generando.value = false
  }
}

async function enviarPedido(id) {
  enviando[id] = true
  try {
    await api.post(`/api/abastecimiento/pedido/${id}/enviar`)
    enviados[id] = true
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `Error al enviar el pedido #${id}`
  } finally {
    enviando[id] = false
  }
}

function reiniciar() {
  cargarSugerencias()
}

onMounted(cargarSugerencias)
</script>
