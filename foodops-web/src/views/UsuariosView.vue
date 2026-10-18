<template>
  <div class="max-w-4xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold text-gray-800">Usuarios</h1>
      <RouterLink to="/dashboard" class="text-sm text-gray-500 hover:text-gray-700">← Dashboard</RouterLink>
    </div>
    <p class="text-sm text-gray-400 mb-4">Crea y administra el acceso de cada tienda</p>

    <!-- Filtros -->
    <div class="flex flex-wrap gap-2 mb-4">
      <select v-model="filtro.punto_id" @change="cargarUsuarios"
        class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
        <option value="">Todas las tiendas</option>
        <option v-for="punto in puntos" :key="punto.id" :value="punto.id">{{ punto.nombre }}</option>
      </select>

      <select v-model="filtro.activo" @change="cargarUsuarios"
        class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
        <option value="">Activos e inactivos</option>
        <option value="true">Solo activos</option>
        <option value="false">Solo inactivos</option>
      </select>

      <button @click="abrirModalNuevo" class="ml-auto bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
        + Nuevo Usuario
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-gray-400">Cargando...</div>

    <!-- Tabla -->
    <div v-else class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="text-left px-3 py-2">Usuario</th>
              <th class="text-left px-3 py-2">Nombre</th>
              <th class="text-left px-3 py-2">Rol</th>
              <th class="text-left px-3 py-2">Tienda</th>
              <th class="text-center px-3 py-2">Estado</th>
              <th class="text-center px-3 py-2">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in usuarios" :key="u.id" class="border-t border-gray-100" :class="{ 'opacity-50': !u.activo }">
              <td class="px-3 py-2 font-medium text-gray-800">{{ u.username }}</td>
              <td class="px-3 py-2 text-gray-600">{{ u.nombre_completo || '—' }}</td>
              <td class="px-3 py-2 text-gray-500">{{ etiquetaRol(u.rol) }}</td>
              <td class="px-3 py-2 text-gray-500">{{ u.punto_nombre || '(todas)' }}</td>
              <td class="px-3 py-2 text-center">
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full"
                  :class="u.activo ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-500'">
                  {{ u.activo ? 'Activo' : 'Inactivo' }}
                </span>
              </td>
              <td class="px-3 py-2 text-center whitespace-nowrap">
                <button @click="editar(u)" title="Editar" class="text-blue-500 hover:text-blue-700 px-1">✏️</button>
                <button v-if="u.id !== auth.user?.user_id" @click="toggleActivo(u)"
                  :title="u.activo ? 'Desactivar' : 'Reactivar'" class="px-1">
                  {{ u.activo ? '🚫' : '✅' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="usuarios.length === 0" class="px-3 py-8 text-center text-sm text-gray-400">
        Sin usuarios para este filtro
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
            <label class="text-xs text-gray-500 block mb-1">Usuario</label>
            <input v-model="form.username" type="text" :disabled="modalEditar" placeholder="Ej: vendedor_jordan"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 disabled:bg-gray-100 disabled:text-gray-500" />
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Email</label>
            <input v-model="form.email" type="email" placeholder="Ej: vendedor.jordan@foodops.gt"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Nombre completo</label>
            <input v-model="form.nombre_completo" type="text" placeholder="Ej: Vendedor Jordán"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>

          <div>
            <label class="text-xs text-gray-500 block mb-1">Rol</label>
            <select v-model="form.rol"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
              <option value="" disabled>Selecciona un rol</option>
              <option v-for="r in ROLES" :key="r.valor" :value="r.valor">{{ r.etiqueta }}</option>
            </select>
          </div>

          <div v-if="!rolMultitienda">
            <label class="text-xs text-gray-500 block mb-1">Tienda</label>
            <select v-model="form.punto_id"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400">
              <option :value="null" disabled>Selecciona una tienda</option>
              <option v-for="punto in puntos" :key="punto.id" :value="punto.id">{{ punto.nombre }}</option>
            </select>
          </div>
          <p v-else class="text-xs text-gray-400">
            Este rol ve todas las tiendas; no necesita una asignada.
          </p>

          <div>
            <label class="text-xs text-gray-500 block mb-1">
              {{ modalEditar ? 'Nueva contraseña (dejar vacío para no cambiarla)' : 'Contraseña' }}
            </label>
            <input v-model="form.password" type="text" placeholder="Mínimo 8 caracteres"
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
import { useAuthStore } from '@/store/index'

const auth = useAuthStore()

// Mismo set que ROLES_MULTI_TIENDA en core/auth.py - estos roles no
// necesitan (ni aceptan en el form) una tienda asignada.
const ROLES_SIN_TIENDA = ['admin', 'gerente_general', 'gerente_central']

const ROLES = [
  { valor: 'admin', etiqueta: 'Administrador (todas las tiendas)' },
  { valor: 'gerente_general', etiqueta: 'Gerente General (todas las tiendas)' },
  { valor: 'gerente_central', etiqueta: 'Gerente Central (abastecimiento, todas las tiendas)' },
  { valor: 'gerente_punto', etiqueta: 'Gerente de Tienda' },
  { valor: 'resp_tienda', etiqueta: 'Responsable de Tienda' },
  { valor: 'repartidor', etiqueta: 'Repartidor' },
  { valor: 'tomador_orden', etiqueta: 'Vendedor / Tomador de Orden' },
  { valor: 'cocinero', etiqueta: 'Cocinero' },
  { valor: 'bodeguero', etiqueta: 'Bodeguero' },
]
function etiquetaRol(valor) {
  return ROLES.find((r) => r.valor === valor)?.etiqueta || valor
}

const puntos = ref([])
const usuarios = ref([])
const loading = ref(true)
const errorMsg = ref('')
const filtro = reactive({ punto_id: '', activo: '' })

const modalAbierto = ref(false)
const modalEditar = ref(false)
const modalTitulo = computed(() => modalEditar.value ? 'Editar Usuario' : 'Nuevo Usuario')
const modalError = ref('')
const guardando = ref(false)
const usuarioEditandoId = ref(null)

function formularioVacio() {
  return { username: '', email: '', nombre_completo: '', rol: '', punto_id: null, password: '' }
}
const form = reactive(formularioVacio())
const rolMultitienda = computed(() => ROLES_SIN_TIENDA.includes(form.rol))

async function cargarPuntos() {
  try {
    const { data } = await api.get('/api/puntos-venta')
    puntos.value = data
  } catch {
    puntos.value = []
  }
}

async function cargarUsuarios() {
  errorMsg.value = ''
  try {
    const params = {}
    if (filtro.punto_id) params.punto_id = filtro.punto_id
    if (filtro.activo) params.activo = filtro.activo
    const { data } = await api.get('/api/auth/usuarios', { params })
    usuarios.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Error al cargar los usuarios'
  }
}

function abrirModalNuevo() {
  modalEditar.value = false
  modalError.value = ''
  usuarioEditandoId.value = null
  Object.assign(form, formularioVacio())
  modalAbierto.value = true
}

function editar(u) {
  modalEditar.value = true
  modalError.value = ''
  usuarioEditandoId.value = u.id
  Object.assign(form, {
    username: u.username,
    email: u.email,
    nombre_completo: u.nombre_completo || '',
    rol: u.rol,
    punto_id: u.punto_id,
    password: '',
  })
  modalAbierto.value = true
}

function cerrarModal() {
  modalAbierto.value = false
}

async function guardar() {
  modalError.value = ''
  if (!form.username.trim() || !form.email.trim() || !form.rol) {
    modalError.value = 'Usuario, email y rol son requeridos'
    return
  }
  if (!rolMultitienda.value && !form.punto_id) {
    modalError.value = 'Este rol necesita una tienda asignada'
    return
  }
  if (!modalEditar.value && form.password.length < 8) {
    modalError.value = 'La contraseña debe tener al menos 8 caracteres'
    return
  }
  if (form.password && form.password.length < 8) {
    modalError.value = 'La contraseña debe tener al menos 8 caracteres'
    return
  }

  guardando.value = true
  try {
    if (modalEditar.value) {
      const body = {
        nombre_completo: form.nombre_completo,
        rol: form.rol,
        punto_id: rolMultitienda.value ? null : form.punto_id,
      }
      if (form.password) body.password = form.password
      await api.patch(`/api/auth/usuarios/${usuarioEditandoId.value}`, body)
    } else {
      await api.post('/api/auth/usuarios', {
        username: form.username,
        email: form.email,
        password: form.password,
        nombre_completo: form.nombre_completo || null,
        rol: form.rol,
        punto_id: rolMultitienda.value ? null : form.punto_id,
      })
    }
    cerrarModal()
    await cargarUsuarios()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Error al guardar el usuario'
  } finally {
    guardando.value = false
  }
}

async function toggleActivo(u) {
  const accion = u.activo ? 'desactivar' : 'reactivar'
  if (!confirm(`¿${accion.charAt(0).toUpperCase() + accion.slice(1)} a ${u.username}?`)) return
  errorMsg.value = ''
  try {
    await api.patch(`/api/auth/usuarios/${u.id}`, { activo: !u.activo })
    await cargarUsuarios()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || `Error al ${accion} el usuario`
  }
}

onMounted(async () => {
  loading.value = true
  await Promise.all([cargarPuntos(), cargarUsuarios()])
  loading.value = false
})
</script>
