<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <div class="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-900 to-gray-800">
      <div class="absolute top-0 right-0 w-96 h-96 bg-green-500/5 rounded-full blur-3xl"></div>
      <div class="absolute bottom-0 left-0 w-80 h-80 bg-green-600/5 rounded-full blur-3xl"></div>
    </div>
    <div class="absolute inset-0 opacity-[0.03]" style="background-image: url('data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'1\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E');"></div>

    <div class="relative z-10 w-full max-w-md px-4">
      <div class="bg-gray-800/90 backdrop-blur-sm border border-gray-700 rounded-2xl shadow-2xl shadow-green-900/10 p-8">
        <div class="text-center mb-8">
          <div class="text-4xl mb-3">⚽</div>
          <h1 class="text-2xl font-bold text-white">
            {{ step === 1 ? t('auth.forgotTitle') : t('auth.resetTitle') }}
          </h1>
          <p class="text-gray-400 text-sm mt-1">
            {{ step === 1 ? t('auth.forgotSubtitle') : t('auth.resetSubtitle') }}
          </p>
        </div>

        <!-- Step 1: Send code -->
        <form v-if="step === 1" @submit.prevent="handleSendCode" class="space-y-5">
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

          <div v-if="error" class="text-red-400 text-sm text-center">{{ error }}</div>
          <div v-if="sentMessage" class="text-green-400 text-sm text-center">{{ sentMessage }}</div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {{ loading ? t('auth.sending') : t('auth.sendCode') }}
          </button>
        </form>

        <!-- Step 2: Reset password -->
        <form v-else @submit.prevent="handleReset" class="space-y-5">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.verificationCode') }}</label>
            <input
              v-model="code"
              type="text"
              required
              maxlength="6"
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 text-center tracking-[0.5em] font-mono focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              placeholder="000000"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.newPassword') }}</label>
            <input
              v-model="newPassword"
              type="password"
              required
              minlength="6"
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.newPasswordPlaceholder')"
            />
          </div>

          <div v-if="error" class="text-red-400 text-sm text-center">{{ error }}</div>
          <div v-if="success" class="text-green-400 text-sm text-center">{{ success }}</div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {{ loading ? t('auth.resetting') : t('auth.resetPassword') }}
          </button>
        </form>

        <div class="mt-6 text-center">
          <RouterLink to="/login" class="text-sm text-green-500 hover:text-green-400 transition-colors">
            {{ t('auth.backToLogin') }}
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'

const { t } = useI18n()
const router = useRouter()

const step = ref(1)
const email = ref('')
const code = ref('')
const newPassword = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')
const sentMessage = ref('')

async function handleSendCode() {
  loading.value = true
  error.value = ''
  sentMessage.value = ''
  try {
    await api.forgotPassword({ email: email.value })
    sentMessage.value = t('auth.codeSent')
    setTimeout(() => { step.value = 2 }, 1000)
  } catch (e: any) {
    error.value = e.message || t('auth.sendFailed')
  } finally {
    loading.value = false
  }
}

async function handleReset() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    await api.resetPassword({
      email: email.value,
      code: code.value,
      new_password: newPassword.value,
    })
    success.value = t('auth.resetSuccess')
    setTimeout(() => router.push('/login'), 1500)
  } catch (e: any) {
    error.value = e.message || t('auth.resetFailed')
  } finally {
    loading.value = false
  }
}
</script>
