import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Rutas con semántica propia de tienda, que no deben recibir el selector
// global: las reglas de abastecimiento usan punto_venta_id NULL como "regla
// global" y las vistas centrales trabajan sobre todas las tiendas a la vez.
const SIN_SELECTOR_GLOBAL = [
  '/api/reglas-reabastecimiento',
  '/api/abastecimiento',
  '/api/puntos-venta',
  // El panel de usuarios maneja su propio filtro de tienda; si no se
  // excluye aquí, el selector global filtraría el listado sin que la
  // pantalla lo muestre, y "Todas las tiendas" dejaría de funcionar.
  '/api/auth/usuarios',
]

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`

  // Inyecta la tienda elegida en el selector de gerencia. Solo en GET, solo si
  // la llamada no trae ya su propio punto_id, y nunca en las rutas de arriba.
  // El backend valida igualmente que el usuario tenga acceso a esa tienda:
  // esto es comodidad de UI, no un control de seguridad.
  const esGet = (config.method || 'get').toLowerCase() === 'get'
  const excluida = SIN_SELECTOR_GLOBAL.some((ruta) => (config.url || '').startsWith(ruta))
  if (esGet && !excluida) {
    const guardado = localStorage.getItem('punto_activo')
    const usuario = JSON.parse(localStorage.getItem('user') || 'null')
    if (guardado && usuario?.ve_todas_las_tiendas) {
      config.params = { punto_id: Number(guardado), ...(config.params || {}) }
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
