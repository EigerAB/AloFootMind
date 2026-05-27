<template>
  <Teleport to="body">
    <div class="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto px-4 py-3 rounded-xl shadow-2xl text-sm max-w-sm flex items-center gap-3"
          :class="toastClass(toast.type)"
        >
          <span>{{ toastIcon(toast.type) }}</span>
          <span>{{ toast.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Toast {
  id: number
  type: 'success' | 'error' | 'info'
  message: string
}

const toasts = ref<Toast[]>([])
let nextId = 0

function toastClass(type: string) {
  return {
    success: 'bg-green-900 border border-green-700 text-green-200',
    error: 'bg-red-900 border border-red-700 text-red-200',
    info: 'bg-blue-900 border border-blue-700 text-blue-200',
  }[type] ?? 'bg-gray-800 text-gray-200'
}

function toastIcon(type: string) {
  return { success: '✅', error: '❌', info: 'ℹ️' }[type] ?? '📢'
}

function show(message: string, type: Toast['type'] = 'info', duration = 3500) {
  const id = nextId++
  toasts.value.push({ id, type, message })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, duration)
}

defineExpose({ show })
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.95);
}
</style>
