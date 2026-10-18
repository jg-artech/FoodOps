<template>
  <div v-if="visible">
    <button v-if="!abierto" @click="abrir"
      class="bg-gray-800 hover:bg-gray-900 text-white text-sm font-semibold px-4 py-2 rounded-xl">
      🗄️ Abrir cajón
    </button>

    <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm p-4">
      <label class="block text-xs text-gray-500 mb-1">Motivo (obligatorio)</label>
      <input v-model="motivo" type="text" maxlength="200" autofocus
        placeholder="Ej. cambio de billete para otro cliente"
        class="w-full border-2 border-gray-300 rounded-xl px-3 py-2 mb-2 text-sm focus:outline-none focus:border-orange-400" />
      <p v-if="modalError" class="text-red-500 text-xs mb-2">{{ modalError }}</p>
      <div class="flex gap-2">
        <button @click="cerrar" class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2 rounded-xl text-sm">
          Cancelar
        </button>
        <button @click="enviar" :disabled="enviando"
          class="flex-1 bg-gray-800 hover:bg-gray-900 text-white font-bold py-2 rounded-xl text-sm disabled:opacity-40">
          {{ enviando ? 'Enviando...' : 'Abrir cajón' }}
        </button>
      </div>
    </div>

    <p v-if="avisoMsg" class="text-green-600 text-xs mt-2">{{ avisoMsg }}</p>
  </div>
</template>

<script setup>
// Botón manual "Abrir cajón" (físico) con motivo obligatorio. No confundir
// con abrir la CAJA financiera del día (/caja). Solo ROLES_ABRIR_CAJON; el
// backend registra cada apertura en audit_log. Nunca se repite solo.
import { computed, ref } from 'vue'
import { useAuthStore } from '@/store/index'
import { ROLES_ABRIR_CAJON, tieneRol } from '@/permisos.js'
import { abrirCajon, normalizarError } from '@/services/impresion.js'

const MOTIVO_MIN = 5

const auth = useAuthStore()
const visible = computed(() => tieneRol(auth.user, ROLES_ABRIR_CAJON))

const abierto = ref(false)
const motivo = ref('')
const modalError = ref('')
const avisoMsg = ref('')
const enviando = ref(false)

function abrir() {
  abierto.value = true
  motivo.value = ''
  modalError.value = ''
  avisoMsg.value = ''
}

function cerrar() {
  abierto.value = false
  modalError.value = ''
}

async function enviar() {
  modalError.value = ''
  const texto = motivo.value.trim()
  if (texto.length < MOTIVO_MIN) {
    modalError.value = `El motivo debe tener al menos ${MOTIVO_MIN} caracteres`
    return
  }
  enviando.value = true
  try {
    await abrirCajon(texto)
    abierto.value = false
    avisoMsg.value = 'Cajón abierto'
  } catch (e) {
    const err = normalizarError(e)
    modalError.value = err.status === 409
      ? 'El cajón no está configurado para esta tienda'
      : err.mensaje
  } finally {
    enviando.value = false
  }
}
</script>
