import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useLoadingStore = defineStore('loading', () => {
  const active = ref(0)

  const isLoading = computed(() => active.value > 0)

  function start() {
    active.value++
  }

  function stop() {
    active.value = Math.max(0, active.value - 1)
  }

  return { isLoading, start, stop }
})
