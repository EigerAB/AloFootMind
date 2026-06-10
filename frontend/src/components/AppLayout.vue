<template>
  <div class="flex h-screen overflow-hidden bg-gray-950 text-gray-100">
    <!-- Sidebar -->
    <aside class="hidden md:flex flex-col w-56 bg-gray-900 border-r border-gray-800 shrink-0 h-full">
      <div class="px-5 py-4 border-b border-gray-800">
        <h1 class="text-lg font-bold text-white tracking-tight">
          <span class="text-green-400">Alo</span>FootMind
        </h1>
        <p class="text-xs text-gray-500 mt-0.5">{{ t('app.tagline') }}</p>
      </div>
      <nav class="flex flex-col gap-1 p-3 flex-1 overflow-y-auto">
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

        <!-- AI 问答 expandable -->
        <div>
          <RouterLink
            to="/chat"
            class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
            active-class="bg-green-900/40 text-green-400 font-medium"
          >
            <span class="text-base">💬</span>
            {{ t('nav.chat') }}
          </RouterLink>
          <!-- Expanded session list -->
          <div v-if="isChatRoute" class="ml-2 mt-1 space-y-0.5">
            <button
              @click="newChat"
              class="w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-xs text-gray-500 hover:bg-gray-800 hover:text-green-400 transition-colors"
            >
              <span>➕</span>
              {{ t('chat.newChat') }}
            </button>
            <div
              v-for="s in chatStore.sortedSessions"
              :key="s.id"
              class="group relative"
            >
              <RouterLink
                :to="`/chat/${s.id}`"
                :class="[
                  'flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-colors min-w-0',
                  route.params.id === String(s.id)
                    ? 'bg-gray-800 text-green-400 font-medium'
                    : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
                ]"
              >
                <span class="flex-1 min-w-0 flex flex-col">
                  <span class="truncate">{{ s.name }}</span>
                  <span v-if="s.preview" class="truncate text-gray-600 text-[10px] leading-tight">{{ s.preview.slice(0, 20) }}</span>
                </span>
              </RouterLink>
              <!-- Hover actions -->
              <div
                class="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 bg-gray-800 rounded px-1"
              >
                <button
                  v-if="editingSessionId !== s.id && !showDeleteDialog"
                  @click.stop="startRename(s)"
                  class="p-0.5 text-gray-500 hover:text-green-400"
                  title="Rename"
                >
                  <i class="iconfont icon-edit" style="font-size: 22px;"></i>
                </button>
                <button
                  v-if="editingSessionId !== s.id && !showDeleteDialog"
                  @click.stop="startDelete(s.id)"
                  class="p-0.5 text-gray-500 hover:text-red-400"
                  title="Delete"
                >
                  <i class="iconfont icon-ashbin" style="font-size: 22px;"></i>
                </button>
              </div>
              <!-- Inline rename -->
              <div
                v-if="editingSessionId === s.id"
                class="absolute inset-0 bg-gray-800 rounded-md px-1.5 flex items-center gap-0.5 z-10"
              >
                <input
                  v-model="editingName"
                  @keydown.enter="confirmRename(s.id)"
                  @keydown.escape="editingSessionId = null"
                  class="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded px-1.5 py-1 text-xs text-white focus:outline-none focus:border-green-500"
                  autofocus
                />
                <button
                  @click="confirmRename(s.id)"
                  class="text-xs text-green-400 hover:text-green-300 px-0.5 shrink-0"
                >
                  ✓
                </button>
                <button
                  @click="editingSessionId = null"
                  class="text-xs text-gray-500 hover:text-gray-300 px-0.5 shrink-0"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>
      </nav>

      <ConfirmDialog
        v-model:visible="showLogoutDialog"
        :title="t('auth.logoutConfirmTitle')"
        :message="t('auth.logoutConfirmMsg')"
        icon="👋"
        :confirm-text="t('auth.logout')"
        :cancel-text="t('auth.cancel')"
        confirm-class="flex-1 py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors"
        @confirm="doLogout"
      />

      <ConfirmDialog
        v-model:visible="showDeleteDialog"
        :title="t('chat.confirmDelete')"
        :message="t('chat.confirmDeleteMsg')"
        icon="🗑️"
        :confirm-text="t('chat.yes')"
        :cancel-text="t('chat.no')"
        @confirm="doDelete"
      />

      <ConfirmDialog
        v-model:visible="showLimitDialog"
        :title="t('chat.sessionLimitTitle')"
        :message="t('chat.sessionLimitMsg')"
        icon="⚠️"
        :confirm-text="t('chat.sessionLimitOk')"
        :cancel-text="''"
        confirm-class="w-full py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm font-semibold rounded-lg transition-colors"
      />
      <div class="px-5 py-3 border-t border-gray-800 space-y-3">
        <!-- Auth indicator -->
        <div v-if="authStore.isLoggedIn" class="flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <div class="w-7 h-7 bg-green-700 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0">
              {{ authStore.user?.nickname?.charAt(0).toUpperCase() ?? 'U' }}
            </div>
            <span class="text-sm text-gray-300 truncate">{{ authStore.user?.nickname }}</span>
          </div>
          <button
            @click="handleLogout"
            class="text-xs text-gray-500 hover:text-red-400 transition-colors shrink-0 ml-2"
            title="Logout"
          >
            {{ t('auth.logout') }}
          </button>
        </div>
        <RouterLink
          v-else
          to="/login"
          class="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 transition-colors"
        >
          <span class="text-base">👤</span>
          {{ t('auth.login') }} / {{ t('auth.register') }}
        </RouterLink>

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
        <!-- <p class="text-xs text-gray-600">{{ t('app.dataSource') }}</p> -->
      </div>
    </aside>

    <!-- Mobile top bar -->
    <div class="md:hidden fixed top-0 inset-x-0 z-50 bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between">
      <h1 class="text-base font-bold text-white">
        <span class="text-green-400">Alo</span>FootMind
      </h1>
      <div class="flex items-center gap-2">
        <!-- Mobile auth indicator -->
        <button
          v-if="authStore.isLoggedIn"
          @click="handleLogout"
          class="w-7 h-7 bg-green-700 rounded-full flex items-center justify-center text-xs font-bold text-white"
        >
          {{ authStore.user?.nickname?.charAt(0).toUpperCase() ?? 'U' }}
        </button>
        <RouterLink
          v-else
          to="/login"
          class="text-lg"
        >👤</RouterLink>
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
        <RouterLink
          to="/chat"
          class="px-2 py-1 text-xs text-gray-400 hover:text-white"
          active-class="text-green-400"
        >💬</RouterLink>
      </div>
    </div>

    <!-- Main content -->
    <main class="flex-1 min-w-0 overflow-y-auto md:pt-0 pt-14">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale, type LocaleKey } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { api } from '@/api'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const chatStore = useChatStore()
const router = useRouter()
const route = useRoute()

const isChatRoute = computed(() => route.path.startsWith('/chat'))

function handleLogout() {
  showLogoutDialog.value = true
}

async function doLogout() {
  try {
    const rt = authStore.refreshToken ?? localStorage.getItem('refresh_token') ?? ''
    await api.logout(rt)
  } catch {
    // ignore
  }
  authStore.clearAuth()
  router.push('/login')
}

const navLinks = [
  { to: '/matches', labelKey: 'nav.matches', icon: '⚽' },
  { to: '/pre-match', labelKey: 'nav.preMatch', icon: '🔍' },
]

const editingSessionId = ref<number | null>(null)
const editingName = ref('')
const showLogoutDialog = ref(false)
const showDeleteDialog = ref(false)
const pendingDeleteId = ref<number | null>(null)
const showLimitDialog = ref(false)

const SESSION_LIMIT = 10

function startRename(s: { id: number; name: string }) {
  editingSessionId.value = s.id
  editingName.value = s.name
}

async function confirmRename(id: number) {
  await chatStore.renameSession(id, editingName.value)
  editingSessionId.value = null
}

function startDelete(id: number) {
  pendingDeleteId.value = id
  showDeleteDialog.value = true
}

async function doDelete() {
  if (pendingDeleteId.value !== null) {
    await chatStore.deleteSession(pendingDeleteId.value)
    pendingDeleteId.value = null
  }
}

function newChat() {
  if (chatStore.sessions.length >= SESSION_LIMIT) {
    showLimitDialog.value = true
    return
  }
  router.push('/chat')
}

function switchLocale(lang: LocaleKey) {
  setLocale(lang)
}

onMounted(() => {
  if (authStore.isLoggedIn) {
    chatStore.loadSessions()
  }
})
</script>
