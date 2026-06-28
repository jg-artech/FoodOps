<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <NavBar v-if="auth.isAuthenticated && !route.meta.noNav" />
    <div class="flex-1">
      <RouterView />
    </div>
    <footer v-if="!route.meta.noNav" class="text-center text-xs text-gray-400 py-3 border-t border-gray-200 bg-white">
      &copy; {{ year }} Artech &mdash;
      <a href="mailto:servicio@artechgt.com" class="hover:text-orange-500 transition">servicio@artechgt.com</a>
    </footer>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/store/index'
import { useRoute } from 'vue-router'
import NavBar from '@/components/NavBar.vue'

const auth = useAuthStore()
const route = useRoute()
const year = new Date().getFullYear()
</script>
