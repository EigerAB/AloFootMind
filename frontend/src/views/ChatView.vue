<template>
  <div class="flex flex-col h-screen">
    <!-- Header -->
    <div class="bg-gray-900 border-b border-gray-800 px-6 py-4 shrink-0 flex items-center justify-between">
      <div>
        <h2 class="text-lg font-bold text-white">{{ t('chat.title') }}</h2>
        <p class="text-xs text-gray-500 mt-0.5">{{ t('chat.subtitle') }}</p>
      </div>
      <button
        @click="startNewChat"
        class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors flex items-center gap-1.5"
      >
        <span>➕</span>
        {{ t('chat.newChat') }}
      </button>
    </div>

    <!-- Messages -->
    <div ref="messagesContainer" class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      <!-- Welcome -->
      <div v-if="messages.length === 0" class="text-center py-16">
        <div class="text-5xl mb-4">⚽</div>
        <h3 class="text-white font-semibold text-lg mb-2">{{ t('chat.welcomeTitle') }}</h3>
        <p class="text-gray-500 text-sm max-w-sm mx-auto">{{ t('chat.welcomeDesc') }}</p>
        <div class="mt-6 flex flex-wrap gap-2 justify-center">
          <button
            v-for="suggestion in localeSuggestions"
            :key="suggestion"
            @click="sendMessage(suggestion)"
            class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 text-sm rounded-lg transition-colors"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>

      <!-- Messages -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- System message -->
        <div v-if="msg.role === 'system'" class="flex items-center gap-3 py-1">
          <div class="flex-1 h-px bg-gray-800"></div>
          <span class="text-xs text-gray-600 italic shrink-0">{{ t('chat.userCancelled') }}</span>
          <div class="flex-1 h-px bg-gray-800"></div>
        </div>
        <!-- User message -->
        <div v-else-if="msg.role === 'user'" class="flex justify-end">
          <div class="bg-green-800 text-white text-sm rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg whitespace-pre-wrap">
            {{ msg.content }}
          </div>
        </div>
        <!-- Assistant message -->
        <div v-else class="flex gap-3">
          <div class="w-8 h-8 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-sm">
            🤖
          </div>
          <div class="flex-1 min-w-0">
            <div
              class="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm prose-report max-w-3xl w-fit"
              v-html="renderMarkdown(msg.content === '__INTERRUPTED__' ? t('chat.userCancelled') : msg.content)"
            />
            <div v-if="msg.sources?.length" class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="(s, si) in msg.sources"
                :key="si"
                class="text-xs bg-gray-800 text-gray-500 px-2 py-1 rounded-md"
              >
                📄 {{ s.collection.replace('_', ' ') }}
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- Streaming indicator -->
      <div v-if="isStreaming" class="flex gap-3">
        <div class="w-8 h-8 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center shrink-0 text-sm">🤖</div>
        <div class="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm min-w-32">
          <div
            v-if="streamBuffer"
            class="prose-report"
            v-html="renderMarkdown(streamBuffer)"
          />
          <div v-else class="flex gap-1 py-1">
            <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
            <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
            <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="bg-gray-900 border-t border-gray-800 px-6 py-4 shrink-0">
      <div class="max-w-4xl mx-auto">
        <div
          v-if="authStore.isGuest"
          class="mb-3 px-4 py-2 bg-amber-900/20 border border-amber-700/30 rounded-lg text-xs text-amber-400 text-center"
        >
          您当前是访客客户，无法发送消息
        </div>
        <div class="flex gap-3">
          <textarea
            ref="inputRef"
            v-model="inputText"
            @keydown.enter="handleEnter"
            @input="adjustHeight"
            :disabled="isStreaming || authStore.isGuest"
            :placeholder="authStore.isGuest ? '访客客户无法发送消息' : t('chat.inputPlaceholder')"
            rows="1"
            class="flex-1 bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-xl px-4 py-3 focus:ring-1 focus:ring-green-500 focus:outline-none disabled:opacity-50 resize-none overflow-y-auto"
          />
          <button
            v-if="!isStreaming"
            @click="sendMessage()"
            :disabled="!inputText.trim() || authStore.isGuest"
            class="px-5 py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white rounded-xl transition-colors font-medium"
          >
            {{ t('chat.sendBtn') }}
          </button>
          <button
            v-else
            @click="handleStop"
            class="px-5 py-3 bg-red-700 hover:bg-red-600 text-white rounded-xl transition-colors font-medium"
          >
            {{ t('chat.stop') }}
          </button>
        </div>
      </div>
    </div>
    <AuthModal v-model:visible="showAuthModal" />
    <ToastNotification ref="toastRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useSseStream } from '@/composables/useSseStream'
import { useMarkdown } from '@/composables/useMarkdown'
import { api, type ChatMessage, type QaMeta } from '@/api'
import AuthModal from '@/components/AuthModal.vue'
import ToastNotification from '@/components/ToastNotification.vue'

const { t, tm } = useI18n()
const authStore = useAuthStore()
const chatStore = useChatStore()
const route = useRoute()
const router = useRouter()
const showAuthModal = ref(false)
const localeSuggestions = computed(() => tm('chat.suggestions') as string[])

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  sources?: { text: string; collection: string }[]
}

const messages = ref<Message[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamBuffer = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

const sessionId = computed(() => {
  const id = route.params.id
  return id ? Number(id) : null
})

// qa_meta for cross-turn football-intent tracking
const qaMeta = ref<QaMeta>({
  football_intent_count: 0,
  generic_turn_count: 0,
})

const streamingSessionId = ref<number | null>(null)

const { post: postSse, stop: stopSse } = useSseStream()
const { render: renderMarkdown } = useMarkdown()

async function loadSession(id: number) {
  const res = await api.loadChatSession(id)
  if (res) {
    messages.value = res.messages.map((m: ChatMessage) => ({
      role: m.role,
      content: m.content,
      sources: m.sources,
    }))
    qaMeta.value = res.qa_meta
  } else {
    messages.value = []
    qaMeta.value = { football_intent_count: 0, generic_turn_count: 0 }
  }
}

watch(
  () => route.params.id,
  async (newId, oldId) => {
    // Abort only when navigating away from the session that is currently streaming
    if (isStreaming.value && newId !== oldId) {
      abortStream()
      // Fire-and-forget: persist the local messages (including __INTERRUPTED__) to the backend
      if (streamingSessionId.value) {
        api.cancelChatSession(streamingSessionId.value, messages.value).catch(() => {})
      }
    }
    if (newId) {
      await loadSession(Number(newId))
    } else {
      messages.value = []
      qaMeta.value = { football_intent_count: 0, generic_turn_count: 0 }
    }
  },
  { immediate: true }
)

onMounted(() => {
  if (authStore.isLoggedIn) {
    chatStore.loadSessions()
  }
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// Keep scroll pinned to bottom whenever content changes
watch([messages, streamBuffer, isStreaming], scrollToBottom)

const inputRef = ref<HTMLTextAreaElement | null>(null)

function handleEnter(e: KeyboardEvent) {
  if (!e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function adjustHeight() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function abortStream() {
  if (!isStreaming.value) return
  stopSse()
  if (streamingSessionId.value) {
    const last = messages.value[messages.value.length - 1]
    if (!last || last.content !== '__INTERRUPTED__') {
      messages.value.push({ role: 'assistant', content: '__INTERRUPTED__' })
    }
  }
  isStreaming.value = false
  streamBuffer.value = ''
}

async function handleStop() {
  const sid = streamingSessionId.value
  abortStream()
  if (sid) {
    await api.cancelChatSession(sid, messages.value).catch(() => {})
  }
}

async function startNewChat() {
  router.push('/chat')
}

const toastRef = ref<InstanceType<typeof ToastNotification> | null>(null)
const GUEST_MSG = '您当前是访客客户，不允许进行该操作'

function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  toastRef.value?.show(message, type)
}

async function sendMessage(text?: string) {
  if (!authStore.isLoggedIn) {
    showAuthModal.value = true
    return
  }
  if (authStore.isGuest) {
    showToast(GUEST_MSG, 'error')
    return
  }
  const query = (text ?? inputText.value).trim()
  if (!query || isStreaming.value) return

  inputText.value = ''
  nextTick(() => adjustHeight())
  messages.value.push({ role: 'user', content: query })

  // If new chat (no session yet), create session immediately so sidebar updates at once
  let currentSessionId = sessionId.value
  if (!currentSessionId) {
    const newSession = await api.createChatSession(query.slice(0, 30))
    currentSessionId = newSession.id
    chatStore.loadSessions()
  }
  streamingSessionId.value = currentSessionId

  const history = messages.value
    .filter(m => m.role !== 'user' || m.content !== query)
    .slice(-10)
    .map(m => ({ role: m.role, content: m.content }))

  isStreaming.value = true
  streamBuffer.value = ''

  try {
    await postSse(
      '/api/chat',
      {
        query,
        conversation_history: history,
        session_id: currentSessionId,
        qa_meta: qaMeta.value,
      },
      {
        onToken: (token: string) => {
          streamBuffer.value += token
        },
        onEvent: (data) => {
          if ((data as any).token) {
            streamBuffer.value += (data as any).token
          }
        },
        onDone: (data) => {
          messages.value.push({
            role: 'assistant',
            content: streamBuffer.value,
            sources: (data as any).sources ?? [],
          })
          // Persist qa_meta for next turn
          if ((data as any).qa_meta) {
            qaMeta.value = (data as any).qa_meta
          }
          // Update route if new session created
          const returnedSessionId = (data as any).session_id
          if (returnedSessionId && !sessionId.value) {
            router.replace(`/chat/${returnedSessionId}`)
          }
          // Refresh session list in sidebar
          if (authStore.isLoggedIn) {
            chatStore.loadSessions()
          }
          streamBuffer.value = ''
          isStreaming.value = false
          streamingSessionId.value = null
        },
        onError: (err) => {
          messages.value.push({
            role: 'assistant',
            content: `❌ Error: ${err}`,
          })
          streamBuffer.value = ''
          isStreaming.value = false
          streamingSessionId.value = null
        },
      }
    )
  } catch (e: unknown) {
    messages.value.push({ role: 'assistant', content: `❌ ${(e as Error).message}` })
    isStreaming.value = false
  }
}

</script>
