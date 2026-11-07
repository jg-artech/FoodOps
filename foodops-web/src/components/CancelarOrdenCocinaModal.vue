<template>
  <div class="fixed inset-0 bg-black/70 flex items-end sm:items-center justify-center p-3 z-50">
    <form @submit.prevent="enviar" autocomplete="off"
      class="bg-gray-800 border border-gray-600 text-white rounded-2xl w-full max-w-sm p-5 shadow-2xl">
      <p class="font-black text-lg">Cancelar orden</p>
      <p class="text-sm text-gray-300 mb-4">
        {{ orden.numero_orden }} · {{ orden.cliente_nombre || 'Sin nombre' }} · {{ formatQ(orden.total) }}
      </p>

      <label class="block text-sm font-semibold mb-1" for="motivo-cancelacion">Motivo *</label>
      <textarea id="motivo-cancelacion" v-model="motivo" rows="3" :maxlength="MOTIVO_MAX + 20"
        :disabled="enviando" placeholder="Ej: el cliente ya no quiso la orden"
        class="w-full bg-gray-900 border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-400"
        :class="errorMotivo && motivo ? 'border-red-400' : 'border-gray-600'"></textarea>
      <p class="text-xs mb-3" :class="errorMotivo && motivo ? 'text-red-300' : 'text-gray-400'">
        {{ errorMotivo && motivo ? errorMotivo : `Entre ${MOTIVO_MIN} y ${MOTIVO_MAX} caracteres` }}
      </p>

      <label class="block text-sm font-semibold mb-1" for="password-cancelacion">Tu contraseña</label>
      <!-- Contraseña personal de quien cancela. new-password: el navegador no la guarda;
           se borra del estado en cuanto se envía. -->
      <input id="password-cancelacion" ref="campoPassword" v-model="password" type="password"
        autocomplete="new-password" :disabled="enviando"
        class="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400" />

      <p v-if="error" class="text-red-300 text-sm mt-3">{{ error }}</p>

      <div class="flex gap-2 mt-5">
        <button type="button" @click="$emit('cerrar')" :disabled="enviando"
          class="flex-1 border border-gray-500 text-gray-200 font-semibold py-2.5 rounded-xl hover:bg-gray-700">
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

// Mismos límites que CancelarCocinaRequest (schemas.py).
const MOTIVO_MIN = 5
const MOTIVO_MAX = 200

const props = defineProps({
  orden: { type: Object, required: true },
})
const emit = defineEmits(['cerrar', 'cancelada'])

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
  if (status === 409) return `Esta orden no se puede cancelar desde cocina: ${mensaje}`
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
    await api.post(`/api/ordenes/${props.orden.id}/cancelar-cocina`, {
      motivo: motivo.value.trim(),
      password: clave,
    })
    emit('cancelada', props.orden)
  } catch (e) {
    error.value = mensajeDeError(e)
    campoPassword.value?.focus()
  } finally {
    enviando.value = false
  }
}
</script>
