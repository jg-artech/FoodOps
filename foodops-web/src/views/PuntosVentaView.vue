<template>
  <div class="max-w-3xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Puntos de Venta</h1>
      <RouterLink to="/dashboard" class="text-sm text-gray-500 hover:text-gray-700">← Dashboard</RouterLink>
    </div>
    <p class="text-sm text-gray-400 mb-4">Administra las tiendas/sucursales</p>

    <div class="flex mb-4">
      <button @click="abrirModalNuevo" class="ml-auto bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
        + Agregar Tienda
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <!-- Tabla -->
    <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-3 py-2">ID</th>
              <th class="text-left px-3 py-2">Nombre</th>
              <th class="text-left px-3 py-2">Dirección</th>
              <th class="text-left px-3 py-2">Teléfono</th>
              <th class="text-center px-3 py-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="punto in puntos" :key="punto.id" class="border-t border-gray-100">
              <td class="px-3 py-2 text-gray-400">{{ punto.id }}</td>
              <td class="px-3 py-2 font-medium text-gray-800">{{ punto.nombre }}</td>
              <td class="px-3 py-2 text-gray-500">{{ punto.direccion || '—' }}</td>
              <td class="px-3 py-2 text-gray-500">{{ punto.telefono || '—' }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap">
                <button @click="editar(punto)" title="Editar" class="text-blue-500 hover:text-blue-700 px-1">✏️</button>
                <button @click="eliminar(punto.id)" title="Eliminar" class="text-red-400 hover:text-red-600 px-1">🗑️</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="puntos.length === 0" class="px-3 py-8 text-center text-sm text-gray-400">
        Sin tiendas registradas
      </div>
    </div>

    <p v-if="errorMsg" class="text-red-500 text-sm text-center mt-3">{{ errorMsg }}</p>

    <!-- Modal crear/editar -->
    <div v-if="modalAbierto" class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 p-2 sm:p-4">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-2xl flex flex-col max-h-[90vh]">
        <div class="px-5 py-4 border-b border-gray-200 shrink-0">
          <h3 class="font-bold text-gray-800">{{ modalTitulo }}</h3>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <div>
            <label class="text-xs text-gray-500 block mb-1">Nombre</label>
            <input v-model="puntoForm.nombre" type="text" placeholder="Ej: Local Centro"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Dirección</label>
            <input v-model="puntoForm.direccion" type="text" placeholder="Ej: Calle Principal 123"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Teléfono</label>
            <input v-model="puntoForm.telefono" type="text" placeholder="Ej: 7777-1111"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <p v-if="modalError" class="text-red-500 text-xs">{{ modalError }}</p>
        </div>

        <div class="flex gap-3 px-5 py-4 border-t border-gray-200 shrink-0">
          <button @click="cerrarModal"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">Cancelar</button>
          <button @click="guardar" :disabled="guardando"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl disabled:opacity-40">
            {{ guardando ? 'Guardando...' : 'Guardar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/services/api'

const puntos = ref([])
const loading = ref(true)
const errorMsg = ref('')

const modalAbierto = ref(false)
const modalEditar = ref(false)
const modalTitulo = computed(() => modalEditar.value ? 'Editar Tienda' : 'Nueva Tienda')
const modalError = ref('')
const guardando = ref(false)
const puntoEditandoId = ref(null)

function formularioVacio() {
  return { nombre: '', direccion: '', telefono: '' }
}
const puntoForm = reactive(formularioVacio())

async function cargarPuntos() {
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/puntos-venta')
    puntos.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar las tiendas'
  }
}

function abrirModalNuevo() {
  modalEditar.value = false
  modalError.value = ''
  puntoEditandoId.value = null
  Object.assign(puntoForm, formularioVacio())
  modalAbierto.value = true
}

function editar(punto) {
  modalEditar.value = true
  modalError.value = ''
  puntoEditandoId.value = punto.id
  Object.assign(puntoForm, {
    nombre: punto.nombre,
    direccion: punto.direccion || '',
    telefono: punto.telefono || '',
  })
  modalAbierto.value = true
}

function cerrarModal() {
  modalAbierto.value = false
}

async function guardar() {
  modalError.value = ''
  if (!puntoForm.nombre.trim()) {
    modalError.value = 'El nombre es requerido'
    return
  }

  guardando.value = true
  try {
    if (modalEditar.value) {
      await api.patch(`/api/puntos-venta/${puntoEditandoId.value}`, { ...puntoForm })
    } else {
      await api.post('/api/puntos-venta', { ...puntoForm })
    }
    cerrarModal()
    await cargarPuntos()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Error al guardar la tienda'
  } finally {
    guardando.value = false
  }
}

async function eliminar(id) {
  if (!confirm('¿Eliminar esta tienda?')) return
  errorMsg.value = ''
  try {
    await api.delete(`/api/puntos-venta/${id}`)
    await cargarPuntos()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al eliminar la tienda'
  }
}

onMounted(async () => {
  loading.value = true
  await cargarPuntos()
  loading.value = false
})
</script>
