<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Personal de cocina</h1>
      <RouterLink :to="volverA" class="text-sm text-gray-500 hover:text-gray-700">← Volver</RouterLink>
    </div>
    <p class="text-sm text-gray-500 mb-5">
      Quienes aparecen como responsables en Cocina. No se borran: si alguien deja de trabajar, se desactiva.
    </p>

    <!-- Gerencia sin tienda elegida: el personal es por tienda -->
    <div v-if="auth.veTodasLasTiendas && auth.puntoIdEfectivo == null"
      class="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-xl px-4 py-3">
      Elige una tienda en el selector de arriba para ver y administrar su personal de cocina.
    </div>

    <template v-else>
      <!-- Agregar -->
      <form @submit.prevent="agregar" class="bg-white rounded-2xl border border-gray-200 p-4 mb-4 flex gap-2">
        <input v-model="nuevoNombre" maxlength="100" placeholder="Nombre de la persona" autocomplete="off"
          class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <button type="submit" :disabled="!nuevoNombre.trim() || guardando"
          class="bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition disabled:opacity-40">
          Agregar
        </button>
      </form>

      <p v-if="errorMsg" class="text-red-500 text-sm mb-3">{{ errorMsg }}</p>
      <div v-if="cargando" class="text-center py-8 text-gray-400">Cargando...</div>

      <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-400 text-xs uppercase">
            <tr>
              <th class="text-left px-4 py-2">Nombre</th>
              <th class="text-left px-4 py-2">Estado</th>
              <th class="text-right px-4 py-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in personal" :key="p.id" class="border-t border-gray-100">
              <td class="px-4 py-2">
                <input v-if="editandoId === p.id" v-model="nombreEditado" maxlength="100"
                  @keydown.enter.prevent="guardarNombre(p)" @keydown.esc="editandoId = null"
                  class="w-full border border-gray-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
                <span v-else :class="p.activo ? 'text-gray-800 font-medium' : 'text-gray-400'">{{ p.nombre }}</span>
              </td>
              <td class="px-4 py-2">
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full"
                  :class="p.activo ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'">
                  {{ p.activo ? 'Activo' : 'Inactivo' }}
                </span>
              </td>
              <td class="px-4 py-2 text-right whitespace-nowrap">
                <template v-if="editandoId === p.id">
                  <button @click="guardarNombre(p)" :disabled="guardando"
                    class="text-xs bg-orange-500 hover:bg-orange-600 text-white px-2 py-1 rounded font-medium disabled:opacity-40">Guardar</button>
                  <button @click="editandoId = null"
                    class="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Cancelar</button>
                </template>
                <template v-else>
                  <button @click="editar(p)"
                    class="text-xs border border-gray-200 hover:border-orange-300 text-gray-600 px-2 py-1 rounded font-medium">Editar</button>
                  <button @click="cambiarActivo(p)" :disabled="guardando"
                    class="text-xs px-2 py-1 rounded font-medium ml-1 disabled:opacity-40"
                    :class="p.activo ? 'bg-red-50 hover:bg-red-100 text-red-600' : 'bg-green-50 hover:bg-green-100 text-green-700'">
                    {{ p.activo ? 'Desactivar' : 'Reactivar' }}
                  </button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="personal.length === 0" class="px-4 py-6 text-center text-sm text-gray-400">
          Todavía no hay personal de cocina en esta tienda.
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api from '@/services/api'
import { useAuthStore } from '@/store/index'
import { ROLES_GERENCIA, tieneRol } from '@/permisos.js'

const auth = useAuthStore()
const URL = '/api/config/personal-cocina'

const personal = ref([])
const cargando = ref(false)
const guardando = ref(false)
const errorMsg = ref('')
const nuevoNombre = ref('')
const editandoId = ref(null)
const nombreEditado = ref('')

const volverA = computed(() => (tieneRol(auth.user, ROLES_GERENCIA) ? '/pos/config' : '/caja'))

function mensajeError(e, porDefecto) {
  const detalle = e?.response?.data?.detail
  if (Array.isArray(detalle)) return detalle.map((d) => d.msg).join(' · ')
  return detalle || porDefecto
}

// Gerencia indica la tienda del selector; un rol de tienda usa la suya.
function puntoParaEscribir() {
  return auth.veTodasLasTiendas ? auth.puntoIdEfectivo : undefined
}

async function cargar() {
  if (auth.veTodasLasTiendas && auth.puntoIdEfectivo == null) {
    personal.value = []
    return
  }
  cargando.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get(URL, { params: { incluir_inactivos: true } })
    personal.value = data
  } catch (e) {
    errorMsg.value = mensajeError(e, 'No se pudo cargar el personal de cocina')
  } finally {
    cargando.value = false
  }
}

async function agregar() {
  const nombre = nuevoNombre.value.trim()
  if (!nombre) return
  guardando.value = true
  errorMsg.value = ''
  try {
    await api.post(URL, { nombre, punto_id: puntoParaEscribir() })
    nuevoNombre.value = ''
    await cargar()
  } catch (e) {
    errorMsg.value = mensajeError(e, 'No se pudo agregar')
  } finally {
    guardando.value = false
  }
}

function editar(p) {
  editandoId.value = p.id
  nombreEditado.value = p.nombre
}

async function actualizar(p, cambios, porDefecto) {
  guardando.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.patch(`${URL}/${p.id}`, cambios)
    Object.assign(p, data)
    return true
  } catch (e) {
    errorMsg.value = mensajeError(e, porDefecto)
    return false
  } finally {
    guardando.value = false
  }
}

async function guardarNombre(p) {
  const nombre = nombreEditado.value.trim()
  if (!nombre) return
  if (await actualizar(p, { nombre }, 'No se pudo cambiar el nombre')) editandoId.value = null
}

function cambiarActivo(p) {
  if (p.activo && !confirm(`¿Desactivar a ${p.nombre}? Ya no aparecerá en Cocina; sus órdenes anteriores no cambian.`)) return
  actualizar(p, { activo: !p.activo }, 'No se pudo cambiar el estado')
}

// Gerencia: recargar al cambiar de tienda en el selector.
watch(() => auth.puntoIdEfectivo, cargar, { immediate: true })
</script>
