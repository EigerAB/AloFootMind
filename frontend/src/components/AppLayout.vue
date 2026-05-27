<template>
  <div class="flex min-h-screen bg-gray-950 text-gray-100">
    <!-- Sidebar -->
    <aside class="hidden md:flex flex-col w-56 bg-gray-900 border-r border-gray-800 shrink-0">
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
      <div class="px-5 py-3 border-t border-gray-800 space-y-2">
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
    <main class="flex-1 min-w-0 md:pt-0 pt-14">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale, type LocaleKey } from '@/i18n'

const { t, locale } = useI18n()

const navLinks = [
  { to: '/matches', labelKey: 'nav.matches', icon: '⚽' },
  { to: '/pre-match', labelKey: 'nav.preMatch', icon: '🔍' },
  { to: '/chat', labelKey: 'nav.chat', icon: '💬' },
]

function switchLocale(lang: LocaleKey) {
  setLocale(lang)
}
</script>
