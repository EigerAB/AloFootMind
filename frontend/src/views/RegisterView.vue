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
          <h1 class="text-2xl font-bold text-white">{{ step === 1 ? t('auth.registerTitle') : t('auth.verifyTitle') }}</h1>
          <p class="text-gray-400 text-sm mt-1">{{ step === 1 ? t('auth.registerSubtitle') : t('auth.verifySubtitle', { email }) }}</p>
        </div>

        <!-- Step 1: Registration form -->
        <form v-if="step === 1" @submit.prevent="handleRegister" class="space-y-5">
          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.nickname') }}</label>
            <input
              v-model="nickname"
              type="text"
              required
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.nicknamePlaceholder')"
            />
          </div>

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
              minlength="6"
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.passwordPlaceholder')"
            />
            <p v-if="passwordHint" class="text-xs text-red-400 mt-1">{{ passwordHint }}</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-1.5">{{ t('auth.confirmPassword') }}</label>
            <input
              v-model="confirmPassword"
              type="password"
              required
              class="w-full bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 focus:ring-2 focus:ring-green-500 focus:border-green-500 focus:outline-none transition-all"
              :placeholder="t('auth.confirmPasswordPlaceholder')"
            />
            <p v-if="confirmHint" class="text-xs text-red-400 mt-1">{{ confirmHint }}</p>
          </div>

          <div v-if="error" class="text-red-400 text-sm text-center">{{ error }}</div>

          <button
            type="submit"
            :disabled="loading || !isFormValid"
            class="w-full bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {{ loading ? t('auth.registering') : t('auth.register') }}
          </button>
        </form>

        <!-- Step 2: Verification code -->
        <form v-else @submit.prevent="handleVerify" class="space-y-5">
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

          <div class="text-center">
            <button
              type="button"
              :disabled="resendCooldown > 0"
              @click="resendCode"
              class="text-sm text-green-500 hover:text-green-400 disabled:text-gray-500 disabled:cursor-not-allowed transition-colors"
            >
              {{ resendCooldown > 0 ? t('auth.resendIn', { seconds: resendCooldown }) : t('auth.resendCode') }}
            </button>
          </div>

          <div v-if="error" class="text-red-400 text-sm text-center">{{ error }}</div>
          <div v-if="success" class="text-green-400 text-sm text-center">{{ success }}</div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-green-700 hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {{ loading ? t('auth.verifying') : t('auth.verify') }}
          </button>

          <button
            type="button"
            @click="step = 1"
            class="w-full text-sm text-gray-400 hover:text-gray-300 transition-colors"
          >
            {{ t('auth.backToRegister') }}
          </button>
        </form>

        <!-- Links -->
        <div v-if="step === 1" class="mt-6 text-center">
          <div class="text-sm text-gray-400">
            {{ t('auth.hasAccount') }}
            <RouterLink to="/login" class="text-green-500 hover:text-green-400 transition-colors">
              {{ t('auth.goLogin') }}
            </RouterLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'

const { t } = useI18n()
const router = useRouter()

const step = ref(1)
const nickname = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const code = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')
const resendCooldown = ref(0)
let cooldownTimer: ReturnType<typeof setInterval> | null = null

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function passwordValid(pwd: string): { valid: boolean; reason?: string } {
  if (pwd.length < 6) return { valid: false, reason: t('auth.pwdTooShort') }
  if (pwd.includes(' ')) return { valid: false, reason: t('auth.pwdHasSpace') }
  if (/[^a-zA-Z0-9\u4e00-\u9fa5]/.test(pwd)) return { valid: false, reason: t('auth.pwdHasSpecial') }
  const hasChinese = /[\u4e00-\u9fa5]/.test(pwd)
  const maxLen = hasChinese ? 7 : 15
  if (pwd.length > maxLen) return { valid: false, reason: t('auth.pwdTooLong', { max: maxLen }) }
  return { valid: true }
}

const isFormValid = computed(() => {
  if (!nickname.value.trim()) return false
  if (!emailRegex.test(email.value)) return false
  const pwdCheck = passwordValid(password.value)
  if (!pwdCheck.valid) return false
  if (password.value !== confirmPassword.value) return false
  return true
})

const passwordHint = computed(() => {
  const check = passwordValid(password.value)
  return check.valid ? '' : check.reason
})

const confirmHint = computed(() => {
  if (!confirmPassword.value) return ''
  if (password.value !== confirmPassword.value) return t('auth.pwdMismatch')
  return ''
})

async function handleRegister() {
  loading.value = true
  error.value = ''
  try {
    await api.register({
      email: email.value,
      password: password.value,
      nickname: nickname.value,
    })
    step.value = 2
    startCooldown()
  } catch (e: any) {
    error.value = e.message || t('auth.registerFailed')
  } finally {
    loading.value = false
  }
}

async function handleVerify() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    await api.verifyEmail({ email: email.value, code: code.value })
    success.value = t('auth.verifySuccess')
    setTimeout(() => router.push('/login'), 1500)
  } catch (e: any) {
    error.value = e.message || t('auth.verifyFailed')
  } finally {
    loading.value = false
  }
}

async function resendCode() {
  if (resendCooldown.value > 0) return
  loading.value = true
  error.value = ''
  try {
    await api.register({
      email: email.value,
      password: password.value,
      nickname: nickname.value,
    })
    startCooldown()
  } catch (e: any) {
    error.value = e.message || t('auth.resendFailed')
  } finally {
    loading.value = false
  }
}

function startCooldown() {
  resendCooldown.value = 60
  cooldownTimer = setInterval(() => {
    resendCooldown.value--
    if (resendCooldown.value <= 0 && cooldownTimer) {
      clearInterval(cooldownTimer)
    }
  }, 1000)
}

onUnmounted(() => {
  if (cooldownTimer) clearInterval(cooldownTimer)
})
</script>
