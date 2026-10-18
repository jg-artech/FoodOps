<template>
  <!-- Solo gerencia: el resto de roles opera siempre en su propia tienda y el
       backend la toma del token, así que no hay nada que elegir. -->
  <select
    v-if="auth.veTodasLasTiendas"
    :value="auth.puntoActivo ?? ''"
    @change="cambiar($event.target.value)"
    class="bg-white text-orange-600 text-sm rounded px-2 py-1 font-medium"
    title="Tienda activa"
  >
    <!-- value="" literal, NO :value="null": Vue quita del DOM un atributo
         ligado a null, y un <option> sin atributo value cae al textContent
         como su .value real ("🏪 Todas las tiendas"). cambiar() nunca
         matcheaba eso contra '' o 'null', así que terminaba mandando
         Number("🏪 Todas las tiendas") = NaN -> se guardaba "NaN" en
         localStorage -> la siguiente petición mandaba ?punto_id=NaN -> 422
         -> se caía en silencio al caché viejo en vez de mostrar todo. -->
    <option value="">🏪 Todas las tiendas</option>
    <option v-for="t in tiendas" :key="t.id" :value="t.id">{{ t.nombre }}</option>
  </select>
  <!-- Para los demás, la tienda es informativa -->
  <span v-else-if="auth.nombrePuntoActual" class="opacity-80 text-sm">
    🏪 {{ auth.nombrePuntoActual }}
  </span>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '@/services/api'
import { useAuthStore } from '@/store/index'

const auth = useAuthStore()
const tiendas = ref([])

function cambiar(valor) {
  // El <option> de "Todas" llega como la cadena vacía (ver el value="" del
  // template). El chequeo contra 'null' es solo defensivo.
  auth.seleccionarTienda(valor === '' || valor === 'null' ? null : Number(valor))
  // Recarga para que todas las vistas abiertas vuelvan a pedir sus datos con
  // la tienda nueva, sin tener que cablear un watcher en cada una.
  window.location.reload()
}

onMounted(async () => {
  if (!auth.veTodasLasTiendas) return
  try {
    const { data } = await api.get('/api/puntos-venta')
    tiendas.value = data
  } catch {
    tiendas.value = []
  }
})
</script>
