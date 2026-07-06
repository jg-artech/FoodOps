<template>
  <nav class="bg-orange-500 text-white px-6 py-3 flex items-center justify-between shadow" style="min-height:5rem">
    <div class="flex flex-col items-center">
      <img src="/Logo.png" alt="Logo" class="h-14 w-auto object-contain" />
      <span class="font-bold text-white text-sm tracking-wide leading-none">FoodOps</span>
    </div>
    <div class="flex items-center gap-4 text-sm">
      <RouterLink to="/dashboard" class="hover:underline">Dashboard</RouterLink>
      <RouterLink to="/pos" class="hover:underline">POS</RouterLink>
      <RouterLink to="/ordenes" class="hover:underline">Órdenes</RouterLink>
      <RouterLink to="/caja" class="hover:underline">Caja</RouterLink>
      <RouterLink to="/cocina" target="_blank" class="hover:underline">Cocina</RouterLink>
      <span class="opacity-80">{{ auth.user?.username }}</span>
      <button @click="handleLogout" class="bg-white text-orange-500 px-3 py-1 rounded font-medium hover:bg-orange-50">
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
