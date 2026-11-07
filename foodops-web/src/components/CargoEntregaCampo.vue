<template>
  <div class="text-sm">
    <label class="block font-medium text-gray-700 mb-1">🛵 Cargo de entrega</label>
    <div class="flex items-center gap-2">
      <span class="font-bold text-gray-500">Q</span>
      <input v-model="estado.monto" type="text" inputmode="decimal" placeholder="0.00" autocomplete="off"
        maxlength="12" :disabled="disabled"
        class="w-32 border rounded-lg px-3 py-2 text-right focus:outline-none focus:ring-2 focus:ring-orange-400"
        :class="error ? 'border-red-300' : 'border-gray-300'" />
      <span v-if="tope !== null && tope !== undefined" class="text-xs text-gray-400">
        Tope sin autorización: {{ formatQ(tope) }}
      </span>
    </div>
    <p v-if="error" class="text-red-500 text-xs mt-1">{{ error }}</p>

    <!-- Sobre el tope -->
    <div v-if="!error && sobreTope" class="mt-2 rounded-xl border p-3"
      :class="autorizado || esResponsable ? 'border-green-300 bg-green-50' : 'border-amber-300 bg-amber-50'">
      <p v-if="esResponsable" class="text-green-700 text-xs">
        Supera el tope de la tienda. Queda registrado como autorizado por ti.
      </p>
      <template v-else-if="autorizado">
        <p class="text-green-700 text-xs font-semibold">
          ✓ Autorizado por {{ estado.autorizacion.nombre }} por {{ formatQ(estado.autorizacion.monto) }}
          (válido 5 minutos)
        </p>
      </template>
      <template v-else>
        <p class="text-amber-800 text-xs font-semibold mb-2">
          Supera el tope de {{ formatQ(tope) }}. Un responsable debe autorizarlo con su usuario y contraseña.
        </p>
        <div class="grid grid-cols-2 gap-2">
          <input v-model="credenciales.username" type="text" placeholder="Usuario del responsable"
            autocomplete="off" autocapitalize="off" spellcheck="false" :disabled="enviando"
            class="border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400" />
          <!-- new-password: que el navegador del vendedor no guarde la clave del responsable -->
          <input v-model="credenciales.password" type="password" placeholder="Contraseña"
            autocomplete="new-password" :disabled="enviando" @keyup.enter="autorizar"
            class="border border-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400" />
        </div>
        <p v-if="errorAutorizacion" class="text-red-500 text-xs mt-1">{{ errorAutorizacion }}</p>
        <button @click="autorizar" :disabled="enviando || !credenciales.username || !credenciales.password"
          class="mt-2 w-full bg-amber-500 hover:bg-amber-600 text-white font-semibold py-1.5 rounded-lg disabled:opacity-40">
          {{ enviando ? 'Verificando...' : `Autorizar ${formatQ(monto)}` }}
        </button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import api from '@/services/api'
import { normalizarError } from '@/services/impresion.js'
import { formatQ } from '@/utils/moneda.js'
import {
  VIGENCIA_AUTORIZACION_MS,
  autorizacionVigente,
  errorCargoEntrega,
  montoCargo,
  montoTexto,
  superaTope,
} from '@/utils/cargoEntrega.js'

// estado = { monto: '', autorizacion: null | { token, monto, nombre, expiraLocal } }
// (reactive del padre, mismo patrón que DatosFacturaCampos).
const props = defineProps({
  estado: { type: Object, required: true },
  tope: { type: [String, Number], default: null },
  esResponsable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const error = computed(() => errorCargoEntrega(props.estado.monto))
const monto = computed(() => montoCargo(props.estado.monto))
const sobreTope = computed(() => superaTope(monto.value, props.tope))
// Si cambia el monto, la autorización anterior deja de valer (el token está
// atado al monto exacto) y vuelve a pedirse.
const autorizado = computed(() => autorizacionVigente(props.estado.autorizacion, monto.value))

const credenciales = reactive({ username: '', password: '' })
const errorAutorizacion = ref('')
const enviando = ref(false)

async function autorizar() {
  if (enviando.value || !credenciales.username || !credenciales.password) return
  errorAutorizacion.value = ''
  enviando.value = true
  try {
    const { data } = await api.post('/api/auth/autorizar-cargo-entrega', {
      username: credenciales.username.trim(),
      password: credenciales.password,
      monto: montoTexto(monto.value),
    })
    // eslint-disable-next-line vue/no-mutating-props
    props.estado.autorizacion = {
      token: data.autorizacion_cargo,
      monto: data.monto,
      nombre: data.autorizado_por_nombre,
      // Reloj local: el backend igual rechaza un token vencido.
      expiraLocal: Date.now() + VIGENCIA_AUTORIZACION_MS - 10_000,
    }
    credenciales.username = ''
  } catch (e) {
    errorAutorizacion.value = normalizarError(e).mensaje
  } finally {
    credenciales.password = ''
    enviando.value = false
  }
}
</script>
