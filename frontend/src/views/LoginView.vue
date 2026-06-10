<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <!-- Gradient background -->
    <div class="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-900 to-gray-800">
      <div class="absolute top-0 right-0 w-96 h-96 bg-green-500/5 rounded-full blur-3xl"></div>
      <div class="absolute bottom-0 left-0 w-80 h-80 bg-green-600/5 rounded-full blur-3xl"></div>
    </div>

    <!-- Soccer pattern overlay -->
    <div class="absolute inset-0 opacity-[0.03]" style="background-image: url('data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'1\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E');"></div>

    <!-- Card -->
    <div class="relative z-10 w-full max-w-md px-4">
      <div class="bg-gray-800/90 backdrop-blur-sm border border-gray-700 rounded-2xl shadow-2xl shadow-green-900/10 p-8">
        <!-- Header -->
        <div class="text-center mb-8">
          <div class="text-4xl mb-3">⚽</div>
          <h1 class="text-2xl font-bold text-white">{{ t('auth.loginTitle') }}</h1>
          <p class="text-gray-400 text-sm mt-1">{{ t('auth.loginSubtitle') }}</p>
        </div>

        <!-- Form -->
        <form @submit.prevent="handleLogin" class="space-y-5">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.email') }}</label>
            <input
              v-model="email"
              type="email"
              required
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.emailPlaceholder')"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.password') }}</label>
            <input
              v-model="password"
              type="password"
              required
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.passwordPlaceholder')"
            />
          </div>

          <div v-if="error" class="text-red-400 text-sm text-center">{{ error }}</div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {{ loading ? t('auth.loggingIn') : t('auth.login') }}
          </button>
        </form>

        <!-- Links -->
        <div class="mt-6 text-center space-y-3">
          <div class="flex gap-3">
            <button
              type="button"
              @click="handleGuestLogin"
              :disabled="loading"
              class="flex-1 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              访客登录
            </button>
            <button
              type="button"
              @click="showQrModal = true"
              :disabled="loading"
              class="flex-1 py-2 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              获取体验账号
            </button>
          </div>
          <RouterLink
            to="/forgot-password"
            class="text-sm text-green-500 hover:text-green-400 transition-colors"
          >
            {{ t('auth.forgotPassword') }}
          </RouterLink>
          <div class="text-sm text-gray-400">
            {{ t('auth.noAccount') }}
            <RouterLink to="/register" class="text-green-500 hover:text-green-400 transition-colors">
              {{ t('auth.goRegister') }}
            </RouterLink>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- QR Modal -->
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="showQrModal"
        class="fixed inset-0 z-[100] flex items-center justify-center"
      >
        <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" @click="showQrModal = false"></div>
        <div class="relative z-10 max-w-sm w-full mx-4 text-center">
          <button
            @click="showQrModal = false"
            class="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-gray-700 border border-gray-600 text-white flex items-center justify-center hover:bg-gray-600 transition-colors z-20"
            title="Close"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
          <img :src="qqImg" class="w-full rounded-xl shadow-2xl border border-gray-700" alt="QQ QR Code" />
          <p class="text-gray-300 text-sm mt-3">扫码联系获取体验账号</p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import qqImg from '@/assets/images/qq.jpg'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const showQrModal = ref(false)

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.login({ email: email.value, password: password.value })
    authStore.setTokens(res.access_token, res.refresh_token)
    authStore.setUser(res.user)
    router.push('/matches')
  } catch (e: any) {
    error.value = e.message || t('auth.loginFailed')
  } finally {
    loading.value = false
  }
}

async function handleGuestLogin() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.guestLogin()
    authStore.setUser(res.user)
    authStore.setTokens(res.access_token, res.refresh_token)
    router.push('/matches')
  } catch (e: any) {
    error.value = e.message || '访客登录失败'
  } finally {
    loading.value = false
  }
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
