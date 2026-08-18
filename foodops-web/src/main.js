import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './style.css'
import { registerSW } from 'virtual:pwa-register'

// Fuerza a las pestañas ya abiertas a recargar una sola vez cuando el
// service worker activa una versión nueva, para que nunca queden
// sirviendo un bundle JS desactualizado (ver bug de login en producción).
registerSW({ immediate: true })

let refreshing = false
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return
    refreshing = true
    window.location.reload()
  })
}

createApp(App).use(createPinia()).use(router).mount('#app')
