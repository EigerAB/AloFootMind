<template>
  <div class="flex h-screen overflow-hidden bg-gray-950 text-gray-100">
    <!-- Sidebar -->
    <aside class="hidden md:flex flex-col w-56 bg-gray-900 border-r border-gray-800 shrink-0 h-full">
      <div class="px-5 py-4 border-b border-gray-800">
        <h1 class="text-lg font-bold text-white tracking-tight">
          <span class="text-green-400">Alo</span>FootMind
        </h1>
        <p class="text-xs text-gray-500 mt-0.5">{{ t('app.tagline') }}</p>
      </div>
      <nav class="flex flex-col gap-1 p-3 flex-1">
        <RouterLink
          v-for="link in navLinks"
          :key="link.to"
          :to="link.to"
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
          active-class="bg-green-900/40 text-green-400 font-medium"
        >
          <span class="text-base">{{ link.icon }}</span>
          {{ t(link.labelKey) }}
        </RouterLink>
      </nav>
      <div class="px-5 py-3 border-t border-gray-800 space-y-3">
        <!-- Auth indicator -->
        <div v-if="authStore.isLoggedIn" class="flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <div class="w-7 h-7 bg-green-700 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0">
              {{ authStore.user?.nickname?.charAt(0).toUpperCase() ?? 'U' }}
            </div>
            <span class="text-sm text-gray-300 truncate">{{ authStore.user?.nickname }}</span>
          </div>
          <button
            @click="handleLogout"
            class="text-xs text-gray-500 hover:text-red-400 transition-colors shrink-0 ml-2"
            title="Logout"
          >
            {{ t('auth.logout') }}
          </button>
        </div>
        <RouterLink
          v-else
          to="/login"
          class="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
        >
          <span class="text-base">👤</span>
          {{ t('auth.login') }} / {{ t('auth.register') }}
        </RouterLink>

        <!-- Language switcher -->
        <div class="flex items-center gap-1">
          <button
            @click="switchLocale('zh')"
            :class="[
              'flex-1 py-1 text-xs rounded-md transition-colors',
              locale === 'zh'
                ? 'bg-green-800 text-green-200 font-medium'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
            ]"
          >中文</button>
          <button
            @click="switchLocale('en')"
            :class="[
              'flex-1 py-1 text-xs rounded-md transition-colors',
              locale === 'en'
                ? 'bg-green-800 text-green-200 font-medium'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
            ]"
          >EN</button>
        </div>
        <p class="text-xs text-gray-600">{{ t('app.dataSource') }}</p>
      </div>
    </aside>

    <!-- Mobile top bar -->
    <div class="md:hidden fixed top-0 inset-x-0 z-50 bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between">
      <h1 class="text-base font-bold text-white">
        <span class="text-green-400">Alo</span>FootMind
      </h1>
      <div class="flex items-center gap-2">
        <!-- Mobile auth indicator -->
        <button
          v-if="authStore.isLoggedIn"
          @click="handleLogout"
          class="w-7 h-7 bg-green-700 rounded-full flex items-center justify-center text-xs font-bold text-white"
        >
          {{ authStore.user?.nickname?.charAt(0).toUpperCase() ?? 'U' }}
        </button>
        <RouterLink
          v-else
          to="/login"
          class="text-lg"
        >👤</RouterLink>
        <!-- Mobile language toggle -->
        <button
          @click="switchLocale(locale === 'zh' ? 'en' : 'zh')"
          class="px-2 py-1 text-xs bg-gray-800 text-gray-400 rounded-md hover:text-white transition-colors"
        >{{ locale === 'zh' ? 'EN' : '中文' }}</button>
        <RouterLink
          v-for="link in navLinks"
          :key="link.to"
          :to="link.to"
          class="px-2 py-1 text-xs text-gray-400 hover:text-white"
          active-class="text-green-400"
        >{{ link.icon }}</RouterLink>
      </div>
    </div>

    <!-- Main content -->
    <main class="flex-1 min-w-0 overflow-y-auto md:pt-0 pt-14">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale, type LocaleKey } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const router = useRouter()

async function handleLogout() {
  try {
    await api.logout()
  } catch {
    // ignore
  }
  authStore.clearAuth()
  router.push('/matches')
}

const navLinks = [
  { to: '/matches', labelKey: 'nav.matches', icon: '⚽' },
  { to: '/pre-match', labelKey: 'nav.preMatch', icon: '🔍' },
  { to: '/chat', labelKey: 'nav.chat', icon: '💬' },
]

function switchLocale(lang: LocaleKey) {
  setLocale(lang)
}
</script>
