import { defineStore } from 'pinia'
import api from '@/services/api'

// Tienda activa del selector de gerencia. null = "Todas las tiendas".
// Vive aparte del usuario porque es una preferencia de la sesión, no un dato
// del JWT: el backend nunca confía en ella, solo la usa para filtrar.
const PUNTO_ACTIVO_KEY = 'punto_activo'

function leerPuntoActivo() {
  const guardado = localStorage.getItem(PUNTO_ACTIVO_KEY)
  return guardado ? Number(guardado) : null
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    puntoActivo: leerPuntoActivo(),
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    puntoId: (state) => state.user?.punto_id || null,
    // Solo gerente_general/admin: el backend lo resuelve y lo devuelve en /me,
    // así que el frontend no tiene que duplicar la lista de roles.
    veTodasLasTiendas: (state) => !!state.user?.ve_todas_las_tiendas,
    // Tienda que debe acompañar a las consultas. null = sin filtro: para un
    // rol de tienda el backend usa la suya, y para gerencia significa "todas".
    puntoIdEfectivo: (state) =>
      state.user?.ve_todas_las_tiendas ? state.puntoActivo : null,
    nombrePuntoActual: (state) => state.user?.punto_nombre || null,
  },

  actions: {
    async login(username, password) {
      const { data } = await api.post('/api/auth/login', { username, password })
      this.token = data.access_token
      localStorage.setItem('token', data.access_token)
      await this.fetchMe()
    },

    async fetchMe() {
      const { data } = await api.get('/api/auth/me')
      this.user = data
      localStorage.setItem('user', JSON.stringify(data))
    },

    seleccionarTienda(puntoId) {
      this.puntoActivo = puntoId
      if (puntoId === null) localStorage.removeItem(PUNTO_ACTIVO_KEY)
      else localStorage.setItem(PUNTO_ACTIVO_KEY, String(puntoId))
    },

    logout() {
      this.token = null
      this.user = null
      this.puntoActivo = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      localStorage.removeItem(PUNTO_ACTIVO_KEY)
    },
  },
})
