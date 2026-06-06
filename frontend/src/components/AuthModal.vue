<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="fixed inset-0 z-[100] flex items-center justify-center"
        @click.self="close"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"></div>

        <!-- Modal -->
        <div
          class="relative z-10 bg-gray-800 border border-gray-700 rounded-2xl shadow-2xl shadow-green-900/20 max-w-sm w-full mx-4 p-6 text-center"
        >
          <div class="text-5xl mb-4">🔒</div>
          <h3 class="text-xl font-bold text-white mb-2">{{ t('auth.modalTitle') }}</h3>
          <p class="text-gray-400 text-sm mb-6">{{ t('auth.modalDesc') }}</p>

          <div class="flex flex-col gap-3">
            <button
              @click="goLogin"
              class="w-full bg-green-700 hover:bg-green-600 text-white font-medium py-2.5 rounded-lg transition-colors"
            >
              {{ t('auth.login') }}
            </button>
            <button
              @click="goRegister"
              class="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-2.5 rounded-lg transition-colors"
            >
              {{ t('auth.register') }}
            </button>
            <button
              @click="close"
              class="text-sm text-gray-400 hover:text-gray-300 transition-colors"
            >
              {{ t('auth.cancel') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

function close() {
  emit('update:visible', false)
}

function goLogin() {
  close()
  router.push('/login')
}

function goRegister() {
  close()
  router.push('/register')
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
