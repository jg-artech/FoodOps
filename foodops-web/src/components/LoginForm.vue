<template>
  <form @submit.prevent="handleSubmit" class="space-y-4">
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Usuario</label>
      <input
        v-model="form.username"
        type="text"
        required
        placeholder="usuario"
        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400"
      />
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
      <input
        v-model="form.password"
        type="password"
        required
        placeholder="••••••••"
        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400"
      />
    </div>
    <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
    <button
      type="submit"
      :disabled="loading"
      class="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-2 rounded-lg transition disabled:opacity-50"
    >
      {{ loading ? 'Ingresando...' : 'Ingresar' }}
    </button>
  </form>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useAuthStore } from '@/store/index'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/dashboard')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Error al iniciar sesión'
  } finally {
    loading.value = false
  }
}
</script>
