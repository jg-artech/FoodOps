<template>
  <div class="text-xs">
    <div class="flex flex-wrap items-center gap-2">
      <span class="font-semibold px-2 py-0.5 rounded-full" :class="claseEstado">
        🧾 {{ ETIQUETA_ESTADO_FACTURA[estado] }}
      </span>
      <span v-if="estado !== 'sin' && datos?.nit" class="text-gray-500">NIT {{ datos.nit }}</span>

      <template v-if="esCobrador">
        <button v-if="puedeMarcar" @click="marcarGenerada" :disabled="enviando"
          class="bg-green-600 hover:bg-green-700 text-white font-semibold px-2.5 py-1 rounded-lg disabled:opacity-50">
          {{ enviando ? 'Guardando...' : 'Marcar factura generada' }}
        </button>
        <button v-if="puedeEditar && !editando" @click="abrirEdicion"
          class="text-orange-600 hover:text-orange-700 font-semibold underline">
          {{ estado === 'sin' ? 'Agregar datos de factura' : 'Editar datos fiscales' }}
        </button>
      </template>
    </div>

    <div v-if="editando" class="mt-2 space-y-2">
      <DatosFacturaCampos :datos="borrador" :disabled="enviando" />
      <p v-if="errorEdicion" class="text-red-500 text-sm">{{ errorEdicion }}</p>
      <div class="flex gap-2 justify-end">
        <button @click="editando = false" :disabled="enviando"
          class="px-3 py-1.5 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50">
          Cancelar
        </button>
        <button @click="guardar" :disabled="enviando || !!errorBorrador"
          class="px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg disabled:opacity-50">
          {{ enviando ? 'Guardando...' : 'Guardar' }}
        </button>
      </div>
    </div>

    <p v-if="errorMsg" class="text-red-500 text-sm mt-1">{{ errorMsg }}</p>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import api from '@/services/api'
import { normalizarError } from '@/services/impresion.js'
import { useAuthStore } from '@/store/index'
import { ROLES_CONFIRMAR_COBRO, tieneRol } from '@/permisos.js'
import DatosFacturaCampos from '@/components/DatosFacturaCampos.vue'
import {
  ETIQUETA_ESTADO_FACTURA,
  bodyDatosFactura,
  datosFacturaDesde,
  errorDatosFactura,
  estadoFactura,
} from '@/utils/factura.js'

// Estado de la factura de una orden y, para cobradores, las acciones:
// marcar generada (orden cobrada y no cancelada) y editar datos fiscales
// (solo mientras la factura no esté generada). Los vendedores solo ven el
// estado: capturan los datos únicamente al cobrar (NewOrderView).
const props = defineProps({
  orden: { type: Object, required: true },
})
const emit = defineEmits(['actualizado'])

const auth = useAuthStore()
const esCobrador = computed(() => tieneRol(auth.user, ROLES_CONFIRMAR_COBRO))

// Copia local: al guardar se actualiza aquí sin mutar la prop del padre.
const datos = ref(props.orden.datos_factura || null)
watch(() => props.orden.datos_factura, (v) => { datos.value = v || null })

const estado = computed(() => estadoFactura(datos.value))
const cancelada = computed(() => props.orden.estado === 'cancelado')
const puedeMarcar = computed(() =>
  estado.value === 'pendiente' && props.orden.estado_cobro === 'cobrada' && !cancelada.value
)
const puedeEditar = computed(() => estado.value !== 'generada' && !cancelada.value)

const claseEstado = computed(() => ({
  sin: 'bg-gray-100 text-gray-500',
  pendiente: 'bg-amber-100 text-amber-700',
  generada: 'bg-green-100 text-green-700',
}[estado.value]))

const editando = ref(false)
const borrador = reactive(datosFacturaDesde(null))
const errorBorrador = computed(() => errorDatosFactura(borrador))
const errorEdicion = ref('')
const errorMsg = ref('')
const enviando = ref(false)

function abrirEdicion() {
  Object.assign(borrador, datosFacturaDesde(datos.value))
  // "Agregar datos" desde "Sin factura": el interruptor arranca encendido.
  if (!datos.value) borrador.requiere_factura = true
  errorEdicion.value = ''
  errorMsg.value = ''
  editando.value = true
}

function aplicar(nuevos) {
  datos.value = nuevos
  emit('actualizado', nuevos)
}

async function guardar() {
  errorEdicion.value = errorBorrador.value
  if (errorEdicion.value) return
  enviando.value = true
  try {
    const { data } = await api.put(`/api/ordenes/${props.orden.id}/datos-factura`, bodyDatosFactura(borrador))
    aplicar(data)
    editando.value = false
  } catch (e) {
    // 409 si otro cobrador la marcó generada mientras tanto: se muestra tal cual.
    errorEdicion.value = normalizarError(e).mensaje
  } finally {
    enviando.value = false
  }
}

async function marcarGenerada() {
  if (!confirm(`¿Marcar como generada la factura de ${props.orden.numero_orden}? Después ya no se podrán editar los datos fiscales.`)) return
  errorMsg.value = ''
  enviando.value = true
  try {
    const { data } = await api.post(`/api/ordenes/${props.orden.id}/datos-factura/marcar-generada`)
    aplicar(data)
    editando.value = false
  } catch (e) {
    errorMsg.value = normalizarError(e).mensaje
  } finally {
    enviando.value = false
  }
}
</script>
