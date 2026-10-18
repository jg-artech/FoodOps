<template>
  <div v-if="visible" class="flex items-center gap-2 text-xs">
    <template v-if="errorMsg">
      <span class="text-red-500">{{ errorMsg }}</span>
    </template>
    <template v-else-if="estado">
      <span class="w-2 h-2 rounded-full" :class="estado.conectado ? 'bg-green-500' : 'bg-gray-400'"></span>
      <span :class="estado.conectado ? 'text-green-700' : 'text-gray-500'">
        {{ estado.conectado ? 'Agente conectado' : 'Agente desconectado' }}
      </span>
      <span v-if="!estado.conectado && pendientes > 0" class="text-amber-600">
        · {{ pendientes >= LIMITE ? `${LIMITE}+` : pendientes }}
        {{ pendientes === 1 ? 'trabajo espera' : 'trabajos esperan' }}
      </span>
      <span v-if="!estado.tiene_token" class="text-gray-400">· sin agente configurado</span>
    </template>
  </div>
</template>

<script setup>
// Indicador del agente de impresión de la tienda (solo lectura). Consulta
// GET /agente/estado cada 20 s; si está desconectado, cuenta los trabajos
// PENDIENTE. Para gerencia, la tienda es la del selector (la agrega api.js).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/store/index'
import { ROLES_ESTADO_AGENTE, tieneRol } from '@/permisos.js'
import { estadoAgente, listarTrabajos, normalizarError } from '@/services/impresion.js'

const INTERVALO_MS = 20000
const LIMITE = 100 // GET /trabajos devuelve como máximo 100

const auth = useAuthStore()
const visible = computed(() => tieneRol(auth.user, ROLES_ESTADO_AGENTE))

const estado = ref(null)
const pendientes = ref(0)
const errorMsg = ref('')
let timer = null

async function consultar() {
  try {
    estado.value = await estadoAgente()
    errorMsg.value = ''
    pendientes.value = estado.value.conectado
      ? 0
      : (await listarTrabajos({ estado: 'pendiente' })).length
  } catch (e) {
    const err = normalizarError(e)
    estado.value = null
    // 400: gerencia en "Todas las tiendas" sin tienda propia.
    errorMsg.value = err.status === 400
      ? 'Selecciona una tienda para ver el agente de impresión'
      : `Agente: ${err.mensaje}`
  }
}

onMounted(() => {
  if (!visible.value) return
  consultar()
  timer = setInterval(consultar, INTERVALO_MS)
})
// Gerencia cambia de tienda en el selector: actualizar sin esperar 20 s.
watch(() => auth.puntoActivo, () => { if (visible.value) consultar() })
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
