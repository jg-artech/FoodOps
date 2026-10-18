<template>
  <div v-if="visible" class="text-xs">
    <button @click="alternar" class="text-gray-500 hover:text-gray-700 underline">
      {{ abierto ? 'Ocultar impresiones' : 'Ver impresiones' }}
    </button>
    <div v-if="abierto" class="mt-1 space-y-1">
      <p v-if="cargando" class="text-gray-400">Cargando...</p>
      <p v-else-if="errorMsg" class="text-red-500">{{ errorMsg }}</p>
      <p v-else-if="!trabajos.length" class="text-gray-400">Sin impresiones por agente.</p>
      <div v-for="t in trabajos" :key="t.id" class="flex items-center justify-between gap-2">
        <span :class="claseEstado(t)">
          {{ t.tipo === 'abrir_cajon' ? '🗄️ Cajón' : '🧾 Ticket' }}: {{ etiqueta(t) }}
        </span>
        <button v-if="puedeReintentar(t)" @click="reintentar(t)"
          class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-2 py-0.5 rounded font-medium shrink-0">
          Reintentar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
// Estado de los trabajos de impresión de una orden (GET /trabajos?orden_id).
// Se carga solo al abrirlo, para no hacer una consulta por cada tarjeta.
import { computed, ref } from 'vue'
import { useAuthStore } from '@/store/index'
import { ROLES_ABRIR_CAJON, ROLES_IMPRESION_TICKET, tieneRol } from '@/permisos.js'
import {
  ERROR_CADUCADO,
  listarTrabajos,
  normalizarError,
  reintentarTrabajo,
} from '@/services/impresion.js'

const props = defineProps({
  ordenId: { type: Number, required: true },
})

const auth = useAuthStore()
const visible = computed(() => tieneRol(auth.user, ROLES_IMPRESION_TICKET))

const abierto = ref(false)
const cargando = ref(false)
const errorMsg = ref('')
const trabajos = ref([])

async function cargar() {
  cargando.value = true
  errorMsg.value = ''
  try {
    trabajos.value = await listarTrabajos({ orden_id: props.ordenId })
  } catch (e) {
    errorMsg.value = normalizarError(e).mensaje
  } finally {
    cargando.value = false
  }
}

function alternar() {
  abierto.value = !abierto.value
  if (abierto.value) cargar()
}

function caducado(t) {
  return t.estado === 'error' && t.error === ERROR_CADUCADO
}

function etiqueta(t) {
  if (caducado(t)) return 'Cajón no abierto (venció el tiempo). Usa Abrir cajón si lo necesitas.'
  if (t.estado === 'ok') return t.tipo === 'abrir_cajon' ? 'abierto' : 'impreso'
  if (t.estado === 'error') return `error${t.error ? ` (${t.error})` : ''}`
  return 'pendiente'
}

function claseEstado(t) {
  if (t.estado === 'ok') return 'text-green-600'
  if (t.estado === 'error') return 'text-red-500'
  return 'text-amber-600'
}

// Mismas reglas que el backend: solo trabajos en error no caducados; un
// ABRIR_CAJON solo lo reintenta ROLES_ABRIR_CAJON; un ticket, quien lo creó
// o la gerencia de la tienda (ROLES_ABRIR_CAJON).
function puedeReintentar(t) {
  if (t.estado !== 'error' || caducado(t)) return false
  if (tieneRol(auth.user, ROLES_ABRIR_CAJON)) return true
  return t.tipo === 'ticket' && t.solicitado_por === auth.user?.user_id
}

async function reintentar(t) {
  errorMsg.value = ''
  try {
    await reintentarTrabajo(t.id)
    await cargar()
  } catch (e) {
    errorMsg.value = normalizarError(e).mensaje
  }
}
</script>
