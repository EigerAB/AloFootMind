import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { User } from '@/api'

export { type User }

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null)
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!accessToken.value && !!user.value)

  // Actions
  function setTokens(access: string, refresh: string) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function setUser(u: User) {
    user.value = u
    localStorage.setItem('user', JSON.stringify(u))
  }

  function clearAuth() {
    user.value = null
    accessToken.value = null
    refreshToken.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  function hydrateFromStorage() {
    const at = localStorage.getItem('access_token')
    const rt = localStorage.getItem('refresh_token')
    const u = localStorage.getItem('user')
    if (at) accessToken.value = at
    if (rt) refreshToken.value = rt
    if (u) {
      try {
        user.value = JSON.parse(u)
      } catch {
        user.value = null
      }
    }
  }

  return {
    user,
    accessToken,
    refreshToken,
    isLoggedIn,
    setTokens,
    setUser,
    clearAuth,
    hydrateFromStorage,
  }
})
