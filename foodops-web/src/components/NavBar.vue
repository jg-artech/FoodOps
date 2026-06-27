<template>
  <nav class="bg-orange-500 text-white px-6 py-3 flex items-center justify-between shadow">
    <span class="font-bold text-lg">FoodOps</span>
    <div class="flex items-center gap-4">
      <RouterLink to="/dashboard" class="hover:underline text-sm">Dashboard</RouterLink>
      <RouterLink to="/ordenes" class="hover:underline text-sm">Órdenes</RouterLink>
      <span class="text-sm opacity-80">{{ auth.user?.username }}</span>
      <button @click="handleLogout" class="bg-white text-orange-500 px-3 py-1 rounded text-sm font-medium hover:bg-orange-50">
        Salir
      </button>
    </div>
  </nav>
</template>

<script setup>
import { useAuthStore } from '@/store/index'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
