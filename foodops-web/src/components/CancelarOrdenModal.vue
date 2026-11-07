<template>
  <div class="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center p-3 z-50">
    <form @submit.prevent="enviar" autocomplete="off"
      class="rounded-2xl w-full max-w-sm p-5 shadow-2xl border" :class="c.caja">
      <p class="font-black text-lg">Cancelar orden</p>
      <p class="text-sm mb-4" :class="c.tenue">
        {{ orden.numero_orden }} · {{ orden.cliente_nombre || 'Sin nombre' }} · {{ formatQ(orden.total) }}
      </p>

      <!-- Orden ya pagada (solo llega aquí desde el POS): la devolución queda pendiente -->
      <div v-if="cobrada" class="rounded-lg border px-3 py-2 text-sm mb-4" :class="c.aviso">
        Esta orden ya fue cobrada ({{ METODOS[orden.metodo_pago] || orden.metodo_pago }}).
        Al cancelarla queda pendiente devolver {{ formatQ(orden.total) }} al cliente.
      </div>

      <label class="block text-sm font-semibold mb-1" for="motivo-cancelacion">Motivo *</label>
      <textarea id="motivo-cancelacion" v-model="motivo" rows="3" :maxlength="MOTIVO_MAX + 20"
        :disabled="enviando" placeholder="Ej: el cliente ya no quiso la orden"
        class="w-full border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-400"
        :class="[c.campo, errorMotivo && motivo ? 'border-red-400' : c.borde]"></textarea>
      <p class="text-xs mb-3" :class="errorMotivo && motivo ? c.error : c.tenue">
        {{ errorMotivo && motivo ? errorMotivo : `Entre ${MOTIVO_MIN} y ${MOTIVO_MAX} caracteres` }}
      </p>

      <label class="block text-sm font-semibold mb-1" for="password-cancelacion">Tu contraseña</label>
      <!-- Contraseña personal de quien cancela. new-password: el navegador no la guarda;
           se borra del estado en cuanto se envía. -->
      <input id="password-cancelacion" ref="campoPassword" v-model="password" type="password"
        autocomplete="new-password" :disabled="enviando"
        class="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
        :class="[c.campo, c.borde]" />

      <p v-if="error" class="text-sm mt-3" :class="c.error">{{ error }}</p>

      <div class="flex gap-2 mt-5">
        <button type="button" @click="$emit('cerrar')" :disabled="enviando"
          class="flex-1 border font-semibold py-2.5 rounded-xl" :class="c.volver">
          Volver
        </button>
        <button type="submit" :disabled="enviando || !!errorMotivo || !password"
          class="flex-1 bg-red-500 hover:bg-red-400 text-white font-black py-2.5 rounded-xl disabled:opacity-40">
          {{ enviando ? 'Cancelando...' : 'Cancelar orden' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import api from '@/services/api'
import { normalizarError } from '@/services/impresion.js'
import { formatQ } from '@/utils/moneda.js'

// Cancelación con motivo y contraseña personal, en dos pantallas:
// - origen "cocina": POST /cancelar-cocina (no cancela órdenes cobradas).
// - origen "pos":    POST /cancelar (sí las cancela; la devolución queda pendiente).

// Mismos límites que CancelarCocinaRequest (schemas.py).
const MOTIVO_MIN = 5
const MOTIVO_MAX = 200
const METODOS = { efectivo: 'efectivo', tarjeta: 'tarjeta', transferencia: 'transferencia' }

const props = defineProps({
  orden: { type: Object, required: true },
  origen: { type: String, default: 'cocina', validator: (v) => ['cocina', 'pos'].includes(v) },
})
const emit = defineEmits(['cerrar', 'cancelada'])

// Cocina es oscura; Órdenes (POS) es clara.
const c = computed(() => (props.origen === 'cocina'
  ? {
      caja: 'bg-gray-800 border-gray-600 text-white',
      tenue: 'text-gray-400',
      campo: 'bg-gray-900',
      borde: 'border-gray-600',
      error: 'text-red-300',
      aviso: 'border-amber-500 text-amber-200',
      volver: 'border-gray-500 text-gray-200 hover:bg-gray-700',
    }
  : {
      caja: 'bg-white border-gray-200 text-gray-800',
      tenue: 'text-gray-500',
      campo: 'bg-white',
      borde: 'border-gray-300',
      error: 'text-red-500',
      aviso: 'border-amber-300 bg-amber-50 text-amber-800',
      volver: 'border-gray-300 text-gray-600 hover:bg-gray-50',
    }))

const cobrada = computed(() => props.orden.estado_cobro === 'cobrada')
const ruta = computed(() => (props.origen === 'cocina' ? 'cancelar-cocina' : 'cancelar'))

const motivo = ref('')
const password = ref('')
const enviando = ref(false)
const error = ref('')
const campoPassword = ref(null)

const errorMotivo = computed(() => {
  const n = motivo.value.trim().length
  return n >= MOTIVO_MIN && n <= MOTIVO_MAX ? '' : `El motivo debe tener entre ${MOTIVO_MIN} y ${MOTIVO_MAX} caracteres`
})

function mensajeDeError(e) {
  const { status, mensaje } = normalizarError(e)
  if (status === 401) return 'Contraseña incorrecta'
  if (status === 409 && props.origen === 'cocina') return `Esta orden no se puede cancelar desde cocina: ${mensaje}`
  return mensaje
}

async function enviar() {
  if (enviando.value || errorMotivo.value || !password.value) return
  error.value = ''
  enviando.value = true
  // La contraseña sale del estado en cuanto se envía, salga bien o mal.
  const clave = password.value
  password.value = ''
  try {
    const { data } = await api.post(`/api/ordenes/${props.orden.id}/${ruta.value}`, {
      motivo: motivo.value.trim(),
      password: clave,
    })
    emit('cancelada', props.orden, data)
  } catch (e) {
    error.value = mensajeDeError(e)
    campoPassword.value?.focus()
  } finally {
    enviando.value = false
  }
}
</script>
