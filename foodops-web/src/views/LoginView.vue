<template>
  <div class="flex flex-col items-center justify-center flex-1 bg-gray-100 px-4 py-12">
    <div class="bg-white rounded-2xl shadow-md w-full max-w-sm p-8">
      <div class="text-center mb-6">
        <img src="/Logo.png" alt="Logo" class="h-20 w-auto mx-auto mb-4 object-contain" />
        <h1 class="text-2xl font-bold text-orange-500">FoodOps</h1>
        <p class="text-gray-500 text-sm mt-1">Sistema de gestión de órdenes</p>
      </div>
      <LoginForm />
    </div>

  </div>
</template>

<script setup>
import LoginForm from '@/components/LoginForm.vue'
</script>
