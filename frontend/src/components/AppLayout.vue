<template>
  <div class="flex min-h-screen bg-gray-950 text-gray-100">
    <!-- Sidebar -->
    <aside class="hidden md:flex flex-col w-56 bg-gray-900 border-r border-gray-800 shrink-0">
      <div class="px-5 py-4 border-b border-gray-800">
        <h1 class="text-lg font-bold text-white tracking-tight">
          <span class="text-green-400">Alo</span>FootMind
        </h1>
        <p class="text-xs text-gray-500 mt-0.5">Multi-Agent Football Analysis</p>
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
          {{ link.label }}
        </RouterLink>
      </nav>
      <div class="px-5 py-3 border-t border-gray-800">
        <p class="text-xs text-gray-600">StatsBomb Open Data</p>
      </div>
    </aside>

    <!-- Mobile top bar -->
    <div class="md:hidden fixed top-0 inset-x-0 z-50 bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between">
      <h1 class="text-base font-bold text-white">
        <span class="text-green-400">Alo</span>FootMind
      </h1>
      <div class="flex gap-1">
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

const navLinks = [
  { to: '/matches', label: 'Matches', icon: '⚽' },
  { to: '/pre-match', label: 'Pre-Match Intel', icon: '🔍' },
  { to: '/chat', label: 'AI Chat', icon: '💬' },
]
</script>
