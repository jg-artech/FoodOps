<template>
  <form @submit.prevent="handleSubmit" class="space-y-5">
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Cliente</label>
        <input v-model="form.cliente_nombre" type="text" placeholder="Nombre del cliente"
          class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400" />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
        <input v-model="form.cliente_telefono" type="tel" placeholder="300 000 0000"
          class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400" />
      </div>
    </div>

    <div class="flex items-center gap-6">
      <div class="flex-1">
        <label class="block text-sm font-medium text-gray-700 mb-1">Método de pago *</label>
        <select v-model="form.metodo_pago" required
          class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400">
          <option value="">Seleccionar...</option>
          <option value="efectivo">Efectivo</option>
          <option value="tarjeta">Tarjeta</option>
          <option value="transferencia">Transferencia</option>
        </select>
      </div>
      <label class="flex items-center gap-2 mt-5 cursor-pointer">
        <input v-model="form.es_domicilio" type="checkbox" class="w-4 h-4 accent-orange-500" />
        <span class="text-sm font-medium text-gray-700">Domicilio</span>
      </label>
    </div>

    <div>
      <div class="flex items-center justify-between mb-2">
        <label class="text-sm font-medium text-gray-700">Items *</label>
        <button type="button" @click="addItem"
          class="text-orange-500 text-sm hover:underline font-medium">+ Agregar item</button>
      </div>
      <div v-for="(item, i) in form.items" :key="i" class="grid grid-cols-12 gap-2 mb-2">
        <input v-model="item.producto" placeholder="Producto" required
          class="col-span-4 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <input v-model.number="item.cantidad" type="number" min="1" placeholder="Cant." required
          class="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <input v-model.number="item.precio_unitario" type="number" min="0" step="0.01" placeholder="Precio" required
          class="col-span-3 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <input v-model="item.especiales" placeholder="Notas"
          class="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
        <button type="button" @click="removeItem(i)"
          class="col-span-1 text-red-400 hover:text-red-600 text-lg font-bold leading-none">&times;</button>
      </div>
      <p v-if="form.items.length === 0" class="text-sm text-gray-400">Agrega al menos un item.</p>
    </div>

    <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
    <p v-if="success" class="text-green-600 text-sm font-medium">{{ success }}</p>

    <div class="flex gap-3 justify-end">
      <button type="button" @click="$emit('cancel')"
        class="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
        Cancelar
      </button>
      <button type="submit" :disabled="loading || form.items.length === 0"
        class="px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-lg text-sm transition disabled:opacity-50">
        {{ loading ? 'Guardando...' : 'Crear Orden' }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { ref, reactive } from 'vue'
import api from '@/services/api'

const emit = defineEmits(['created', 'cancel'])

const loading = ref(false)
const error = ref('')
const success = ref('')

const form = reactive({
  cliente_nombre: '',
  cliente_telefono: '',
  metodo_pago: '',
  es_domicilio: false,
  items: [],
})

function addItem() {
  form.items.push({ producto: '', cantidad: 1, precio_unitario: 0, especiales: '' })
}

function removeItem(i) {
  form.items.splice(i, 1)
}

async function handleSubmit() {
  if (!form.metodo_pago) { error.value = 'Selecciona un método de pago.'; return }
  if (form.items.length === 0) { error.value = 'Agrega al menos un item.'; return }

  error.value = ''
  success.value = ''
  loading.value = true

  try {
    const payload = {
      cliente_nombre: form.cliente_nombre || null,
      cliente_telefono: form.cliente_telefono || null,
      metodo_pago: form.metodo_pago,
      es_domicilio: form.es_domicilio,
      items: form.items.map(i => ({
        producto: i.producto,
        cantidad: i.cantidad,
        precio_unitario: i.precio_unitario,
        especiales: i.especiales || null,
      })),
    }
    const { data } = await api.post('/api/ordenes/', payload)
    success.value = `Orden ${data.numero_orden} creada exitosamente.`
    Object.assign(form, { cliente_nombre: '', cliente_telefono: '', metodo_pago: '', es_domicilio: false, items: [] })
    emit('created', data)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Error al crear la orden.'
  } finally {
    loading.value = false
  }
}
</script>
