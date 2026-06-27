<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 px-4">
    <div class="bg-white rounded-2xl shadow-md w-full max-w-sm p-8">
      <div class="text-center mb-6">
        <h1 class="text-2xl font-bold text-orange-500">FoodOps</h1>
        <p class="text-gray-500 text-sm mt-1">Gestión de restaurantes</p>
      </div>
      <LoginForm />
    </div>
  </div>
</template>

<script setup>
import LoginForm from '@/components/LoginForm.vue'
</script>
