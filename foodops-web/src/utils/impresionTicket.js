// Flujo de "Imprimir ticket" compartido por NewOrderView, OrdenList,
// OrderCard y CobrosPendientesView (docs/DISENO_IMPRESION.md §7 y §8).
//
// La venta nunca depende de esto: el cobro ya quedó guardado antes de
// imprimir, y cualquier fallo deja reimprimir después.
//
// - Rol fuera de ROLES_IMPRESION_TICKET (cocinero, repartidor...): window.print()
//   directo, sin llamar al backend, como siempre.
// - 201: "Ticket enviado a impresora" y consulta silenciosa cada 3 s durante
//   20 s; si el trabajo queda en error, "No se pudo imprimir" + Reintentar.
// - 409 IMPRIMIR_INACTIVA: window.print() sin mensaje (tienda sin agente).
// - 409 PENDIENTE_RECIBIR: sin window.print(); se espera la confirmación.
// - 403: sin fallback.
// - Cualquier otro error: se muestra y se ofrece window.print() manual.
import { onBeforeUnmount, ref } from 'vue'
import { useAuthStore } from '@/store/index'
import { ROLES_IMPRESION_TICKET, tieneRol } from '@/permisos.js'
import { imprimirTicket as imprimirEnNavegador } from '@/utils/ticket.js'
import {
  COD_IMPRIMIR_INACTIVA,
  COD_PENDIENTE_RECIBIR,
  imprimirTicket,
  listarTrabajos,
  normalizarError,
  reintentarTrabajo,
} from '@/services/impresion.js'

const INTERVALO_MS = 3000
const DURACION_MS = 20000

export const MSG_PENDIENTE_RECIBIR =
  'El cobro aún no ha sido confirmado por el responsable. ' +
  'Imprime el ticket desde Cobros pendientes después de confirmarlo.'

export function useImpresionTicket() {
  const auth = useAuthStore()

  const avisoMsg = ref('')        // informativo (verde)
  const errorMsg = ref('')        // patrón de error de la app (text-red-500)
  const trabajoFallido = ref(null) // trabajo en error -> botón Reintentar
  const ordenManual = ref(null)    // orden para el botón window.print() manual
  const enviando = ref(false)

  let timer = null
  let ordenActual = null

  function detener() {
    if (timer) clearInterval(timer)
    timer = null
  }

  function limpiar() {
    detener()
    avisoMsg.value = ''
    errorMsg.value = ''
    trabajoFallido.value = null
    ordenManual.value = null
  }

  function seguirTrabajo(trabajo) {
    detener()
    const inicio = Date.now()
    timer = setInterval(async () => {
      if (Date.now() - inicio > DURACION_MS) return detener()
      try {
        const lista = await listarTrabajos({ orden_id: trabajo.orden_id })
        const t = lista.find((x) => x.id === trabajo.id)
        if (!t) return
        if (t.estado === 'ok') {
          detener()
          avisoMsg.value = 'Ticket impreso'
        } else if (t.estado === 'error') {
          detener()
          avisoMsg.value = ''
          errorMsg.value = 'No se pudo imprimir'
          trabajoFallido.value = t
        }
      } catch {
        // Consulta silenciosa: un fallo aquí no se muestra.
      }
    }, INTERVALO_MS)
  }

  async function imprimir(orden) {
    limpiar()
    ordenActual = orden
    if (!tieneRol(auth.user, ROLES_IMPRESION_TICKET)) {
      imprimirEnNavegador(orden)
      return
    }
    enviando.value = true
    try {
      const trabajo = await imprimirTicket(orden.id)
      avisoMsg.value = 'Ticket enviado a impresora'
      seguirTrabajo(trabajo)
    } catch (e) {
      const err = normalizarError(e)
      if (err.status === 409 && err.codigo === COD_IMPRIMIR_INACTIVA) {
        imprimirEnNavegador(orden)
      } else if (err.status === 409 && err.codigo === COD_PENDIENTE_RECIBIR) {
        errorMsg.value = MSG_PENDIENTE_RECIBIR
      } else if (err.status === 403) {
        errorMsg.value = 'No tienes permiso para imprimir este ticket'
      } else {
        errorMsg.value = `No se pudo enviar el ticket: ${err.mensaje}`
        ordenManual.value = orden
      }
    } finally {
      enviando.value = false
    }
  }

  async function reintentar() {
    const t = trabajoFallido.value
    if (!t) return
    errorMsg.value = ''
    trabajoFallido.value = null
    try {
      const trabajo = await reintentarTrabajo(t.id)
      avisoMsg.value = 'Ticket enviado a impresora'
      seguirTrabajo(trabajo)
    } catch (e) {
      errorMsg.value = normalizarError(e).mensaje
      if (ordenActual) ordenManual.value = ordenActual
    }
  }

  function imprimirManual() {
    if (ordenManual.value) imprimirEnNavegador(ordenManual.value)
  }

  onBeforeUnmount(detener)

  return {
    avisoMsg, errorMsg, trabajoFallido, ordenManual, enviando,
    imprimir, reintentar, imprimirManual, limpiar,
  }
}
