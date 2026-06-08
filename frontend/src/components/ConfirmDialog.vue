<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 z-[100] flex items-center justify-center"
        @click.self="close"
      >
        <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>
        <div
          class="relative z-10 bg-gray-800 border border-gray-700 rounded-2xl shadow-2xl max-w-sm w-full mx-4 p-6"
        >
          <div class="flex items-center gap-3 mb-3">
            <span class="text-2xl">{{ icon }}</span>
            <h3 class="text-white font-semibold text-base">{{ title }}</h3>
          </div>
          <p class="text-gray-400 text-sm mb-5">{{ message }}</p>
          <div class="flex gap-2">
            <button
              @click="close"
              class="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm font-semibold rounded-lg transition-colors"
            >
              {{ cancelText }}
            </button>
            <button
              @click="confirm"
              :class="confirmClass"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  visible: boolean
  title: string
  message: string
  icon?: string
  confirmText?: string
  cancelText?: string
  confirmClass?: string
}>(), {
  icon: '🗑️',
  confirmText: '确认',
  cancelText: '取消',
  confirmClass: 'flex-1 py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors'
})

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm'): void
}>()

function close() {
  emit('update:visible', false)
}

function confirm() {
  emit('confirm')
  close()
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
