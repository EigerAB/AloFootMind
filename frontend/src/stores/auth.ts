import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { User } from '@/api'

export { type User }

function isTempUser(u: User | null): boolean {
  return u?.role === 'guest'
}

function _store(key: string, value: string | null, temp: boolean) {
  if (value === null) {
    ;(temp ? sessionStorage : localStorage).removeItem(key)
  } else {
    ;(temp ? sessionStorage : localStorage).setItem(key, value)
  }
}

function _load(key: string): string | null {
  return sessionStorage.getItem(key) || localStorage.getItem(key)
}

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null)
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!accessToken.value && !!user.value)
  const isGuest = computed(() => user.value?.role === 'guest')
  const isTrial = computed(() => user.value?.role === 'trial')
  const isFullUser = computed(() => user.value?.role === 'full' || !user.value?.role)
  const canAnalyze = computed(() => !isGuest.value && !isTrial.value)
  const canGeneratePreMatch = computed(() => !isGuest.value && !isTrial.value)
  const canChat = computed(() => !isGuest.value)

  // Actions
  function setTokens(access: string, refresh: string) {
    const temp = isTempUser(user.value)
    accessToken.value = access
    refreshToken.value = refresh
    _store('access_token', access, temp)
    _store('refresh_token', refresh, temp)
  }

  function setUser(u: User) {
    const temp = isTempUser(u)
    user.value = u
    _store('user', JSON.stringify(u), temp)
  }

  function clearAuth() {
    user.value = null
    accessToken.value = null
    refreshToken.value = null
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('refresh_token')
    sessionStorage.removeItem('user')
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  function hydrateFromStorage() {
    const at = _load('access_token')
    const rt = _load('refresh_token')
    const u = _load('user')
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
    isGuest,
    isTrial,
    isFullUser,
    canAnalyze,
    canGeneratePreMatch,
    canChat,
    setTokens,
    setUser,
    clearAuth,
    hydrateFromStorage,
  }
})
