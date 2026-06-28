<template>
  <form @submit.prevent="handleSubmit" class="space-y-4">
    <div v-if="isOffline" class="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-700">
      Sin conexión. El inicio de sesión requiere internet.
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">Usuario</label>
      <input
        v-model="form.username"
        type="text"
        required
        autocomplete="username"
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
        autocomplete="current-password"
        placeholder="••••••••"
        class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400"
      />
    </div>
    <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
    <button
      type="submit"
      :disabled="loading || isOffline"
      class="w-full bg-orange-500 hover:bg-orange-600 text-white font-semibold py-2 rounded-lg transition disabled:opacity-50"
    >
      {{ loading ? 'Ingresando...' : 'Ingresar' }}
    </button>
  </form>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/store/index'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')
const isOffline = ref(!navigator.onLine)

function updateOnlineStatus() {
  isOffline.value = !navigator.onLine
}

onMounted(() => {
  window.addEventListener('online', updateOnlineStatus)
  window.addEventListener('offline', updateOnlineStatus)
})

onUnmounted(() => {
  window.removeEventListener('online', updateOnlineStatus)
  window.removeEventListener('offline', updateOnlineStatus)
})

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/dashboard')
  } catch (e) {
    if (!navigator.onLine) {
      error.value = 'Sin conexión a internet. Intenta cuando tengas red.'
    } else {
      error.value = e.response?.data?.detail || 'Usuario o contraseña incorrectos'
    }
  } finally {
    loading.value = false
  }
}
</script>
