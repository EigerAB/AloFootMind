<script setup lang="ts">
import { useLoadingStore } from '@/stores/loading'

const store = useLoadingStore()
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-from-class="opacity-0"
      enter-active-class="transition-opacity duration-200"
      enter-to-class="opacity-100"
      leave-from-class="opacity-100"
      leave-active-class="transition-opacity duration-200"
      leave-to-class="opacity-0"
    >
      <div
        v-if="store.isLoading"
        class="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-gray-950/80 backdrop-blur-sm"
      >
        <div class="relative">
          <div class="w-14 h-14 border-4 border-gray-700 border-t-green-500 rounded-full animate-spin" />
        </div>
        <p class="mt-4 text-sm text-gray-400 tracking-wide">Loading...</p>
      </div>
    </Transition>
  </Teleport>
</template>
