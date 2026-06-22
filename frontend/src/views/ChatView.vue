<template>
  <div class="flex flex-col h-screen relative">
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
    <div ref="messagesContainer" class="flex-1 overflow-y-auto px-6 py-4 space-y-4" @scroll.passive="onContainerScroll">
      <!-- Load more -->
      <div v-if="hasMore" class="flex justify-center pt-2 pb-1">
        <button
          @click="loadMore"
          class="px-4 py-1.5 text-xs text-gray-500 hover:text-gray-300 bg-gray-800/60 hover:bg-gray-700/60 border border-gray-700/50 rounded-full transition-colors"
        >⬆ {{ t('chat.loadMore') }}</button>
      </div>

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
          <div class="min-w-0 max-w-3xl overflow-hidden">
            <div class="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm overflow-hidden">
              <!-- Thinking panel (embedded inside the message) -->
              <div v-if="msg.thinking" class="border-b border-gray-800 px-3 py-2.5">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-1.5">
                    <span v-if="!msg.thinking.completed" class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse"></span>
                    <span v-else class="w-2 h-2 rounded-full bg-green-500"></span>
                    <span class="text-xs font-medium text-gray-400">
                      {{ msg.thinking.completed ? t('chat.thinkingDone') : t('chat.thinking') }}
                    </span>
                  </div>
                  <button
                    @click="() => { msg.thinking!.collapsed = !msg.thinking!.collapsed; autoScroll.value = false }"
                    class="text-xs text-gray-600 hover:text-gray-400 transition-colors px-1"
                  >{{ msg.thinking.collapsed ? '▼' : '▲' }}</button>
                </div>
                <div v-if="!msg.thinking.collapsed" class="space-y-1">
                  <div
                    v-for="step in msg.thinking.steps"
                    :key="step.node_name"
                    class="rounded-lg border px-2.5 py-1.5 text-xs transition-all"
                    :class="stepRowClass(step.status)"
                  >
                    <div class="flex items-center gap-2">
                      <span class="shrink-0 w-4 text-center">
                        <span v-if="step.status === 'started'" class="inline-block w-3 h-3 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></span>
                        <span v-else-if="step.status === 'completed'" class="text-green-400">✓</span>
                        <span v-else class="text-red-400">✕</span>
                      </span>
                      <span class="font-medium" :class="stepNameClass(step.status)">{{ translateStepNode(step.node_name) }}</span>
                    </div>
                    <div v-if="step.summary" class="mt-0.5 ml-6 text-gray-400 break-all">{{ step.summary }}</div>
                    <details v-if="step.data" class="mt-1 ml-6">
                      <summary class="cursor-pointer text-gray-600 hover:text-gray-400 select-none">data</summary>
                      <pre class="mt-1 text-[10px] text-gray-500 whitespace-pre-wrap break-all">{{ JSON.stringify(step.data, null, 2) }}</pre>
                    </details>
                  </div>
                  <div v-if="msg.thinking.ragContext.length > 0" class="mt-2 pt-2 border-t border-gray-800">
                    <button
                      @click="msg.thinking.ragCollapsed = !msg.thinking.ragCollapsed"
                      class="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors mb-1"
                    >
                      <span>📄</span>
                      <span>{{ t('chat.ragSources') }} ({{ msg.thinking.ragContext.length }})</span>
                      <span>{{ msg.thinking.ragCollapsed ? '▼' : '▲' }}</span>
                    </button>
                    <div v-if="!msg.thinking.ragCollapsed" class="space-y-1.5">
                      <div
                        v-for="(s, si) in msg.thinking.ragContext"
                        :key="si"
                        class="text-xs bg-gray-800/60 rounded px-2.5 py-1.5 border border-gray-700/50"
                      >
                        <div class="flex items-center gap-2 mb-1">
                          <span class="text-gray-500">[{{ si + 1 }}]</span>
                          <span class="text-gray-600">{{ s.collection }}</span>
                          <span v-if="s.score !== undefined" class="ml-auto text-gray-500">
                            score: {{ s.score.toFixed ? s.score.toFixed(4) : s.score }}
                          </span>
                        </div>
                        <div class="text-gray-400 leading-relaxed">{{ s.text }}</div>
                      </div>
                    </div>
                    <div v-else class="flex flex-wrap gap-1">
                      <span
                        v-for="s in msg.thinking.ragContext"
                        :key="s.collection + s.score"
                        class="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 border border-gray-700/40"
                      >
                        {{ s.collection.replace('_', ' ') }}
                        <span v-if="s.score !== undefined" class="opacity-70">{{ s.score.toFixed ? s.score.toFixed(3) : s.score }}</span>
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <!-- Content -->
              <div
                class="px-4 py-3 text-sm prose-report overflow-hidden"
                v-html="renderMarkdown(msg.content === '__INTERRUPTED__' ? t('chat.userCancelled') : msg.content)"
              />
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Scroll to bottom button -->
    <transition name="fade">
      <button
        v-if="!autoScroll"
        @click="autoScroll = true; forceScrollToBottom()"
        class="absolute bottom-28 right-8 z-10 w-9 h-9 bg-gray-700 hover:bg-gray-600 border border-gray-600 text-gray-300 hover:text-white rounded-full shadow-lg flex items-center justify-center transition-colors"
        title="回到底部"
      >&#x2193;</button>
    </transition>

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
            :disabled="isPlanning || isStreaming || authStore.isGuest"
            :placeholder="authStore.isGuest ? '访客客户无法发送消息' : t('chat.inputPlaceholder')"
            rows="1"
            class="flex-1 bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-xl px-4 py-3 focus:ring-1 focus:ring-green-500 focus:outline-none disabled:opacity-50 resize-none overflow-y-auto"
          />
          <button
            v-if="!isStreaming && !isPlanning"
            @click="sendMessage()"
            :disabled="!inputText.trim() || authStore.isGuest"
            class="px-5 py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white rounded-xl transition-colors font-medium"
          >
            {{ t('chat.sendBtn') }}
          </button>
          <button
            v-else-if="isStreaming"
            @click="handleStop"
            class="px-5 py-3 bg-red-700 hover:bg-red-600 text-white rounded-xl transition-colors font-medium"
          >
            {{ t('chat.stop') }}
          </button>
          <button
            v-else
            disabled
            class="px-5 py-3 bg-gray-700 text-gray-400 rounded-xl transition-colors font-medium cursor-not-allowed"
          >
            {{ t('chat.thinking') }}
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
import { useMarkdown } from '@/composables/useMarkdown'
import { api, type ChatMessage, type QaMeta, type StepEntry, type RagHit, type PlanResponse } from '@/api'
import { useLoadingStore } from '@/stores/loading'
import AuthModal from '@/components/AuthModal.vue'
import ToastNotification from '@/components/ToastNotification.vue'

const { t, tm } = useI18n()
const authStore = useAuthStore()
const chatStore = useChatStore()
const loadingStore = useLoadingStore()
const route = useRoute()
const router = useRouter()
const showAuthModal = ref(false)
const localeSuggestions = computed(() => tm('chat.suggestions') as string[])

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking?: {
    steps: StepEntry[]
    ragContext: RagHit[]
    completed: boolean
    collapsed: boolean
    ragCollapsed: boolean
  }
}

const messages = ref<Message[]>([])
const displayOffset = ref(0)   // how many messages are hidden before current view
const totalMessages = ref(0)   // total messages in session on server
const PAGE_SIZE = 10           // messages per page (5 dialogues × 2)
const hasMore = computed(() => displayOffset.value > 0)

// In-memory cache: sessionId -> { messages, displayOffset, totalMessages, qaMeta }
const sessionCache = new Map<number, {
  messages: Message[]
  displayOffset: number
  totalMessages: number
  qaMeta: QaMeta
}>()
const inputText = ref('')
const isStreaming = ref(false)
const isPlanning = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const autoScroll = ref(true)

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
const streamAbort = ref<(() => void) | null>(null)

// function sourceColorClass(score: number | undefined): string {
//   if (score === undefined) return 'bg-gray-800 text-gray-500'
//   if (score >= 0.3) return 'bg-green-900/40 text-green-400 border-green-700/40'
//   if (score >= 0.15) return 'bg-yellow-900/40 text-yellow-400 border-yellow-700/40'
//   return 'bg-red-900/40 text-red-400 border-red-700/40'
// }

function translateStepNode(nodeName: string): string {
  const key = `agent.nodes.${nodeName}`
  const result = t(key)
  return result === key ? nodeName : result
}

function stepRowClass(status: string) {
  return {
    started: 'bg-yellow-950/30 border-yellow-800/50',
    completed: 'bg-green-950/30 border-green-800/50',
    error: 'bg-red-950/30 border-red-800/50',
    failed: 'bg-red-950/30 border-red-800/50',
  }[status] ?? 'bg-gray-800/30 border-gray-700/50'
}

function stepNameClass(status: string) {
  return {
    started: 'text-yellow-400',
    completed: 'text-green-400',
    error: 'text-red-400',
    failed: 'text-red-400',
  }[status] ?? 'text-gray-400'
}
const { render: renderMarkdown } = useMarkdown()

function mapChatMessage(m: ChatMessage): Message {
  return {
    role: m.role,
    content: m.content,
    thinking: m.thinking ? {
      steps: m.thinking.steps ?? [],
      ragContext: m.thinking.rag_context ?? [],
      completed: true,
      collapsed: true,
      ragCollapsed: true,
    } : undefined,
  }
}

function saveToCache(id: number) {
  sessionCache.set(id, {
    messages: [...messages.value],
    displayOffset: displayOffset.value,
    totalMessages: totalMessages.value,
    qaMeta: { ...qaMeta.value },
  })
}

async function loadSession(id: number) {
  // Restore from cache if available
  const cached = sessionCache.get(id)
  if (cached) {
    messages.value = cached.messages
    displayOffset.value = cached.displayOffset
    totalMessages.value = cached.totalMessages
    qaMeta.value = cached.qaMeta
    return
  }
  loadingStore.start()
  try {
    // First fetch: get total count with limit=1 then fetch last PAGE_SIZE
    const probe = await api.loadChatSession(id, 0, 1)
    if (!probe) {
      messages.value = []
      totalMessages.value = 0
      displayOffset.value = 0
      qaMeta.value = { football_intent_count: 0, generic_turn_count: 0 }
      return
    }
    const total = probe.total
    totalMessages.value = total
    const offset = Math.max(0, total - PAGE_SIZE)
    displayOffset.value = offset
    const res = await api.loadChatSession(id, offset, PAGE_SIZE)
    if (res) {
      messages.value = res.messages.map(mapChatMessage)
      qaMeta.value = res.qa_meta
    }
  } finally {
    loadingStore.stop()
  }
}

async function loadMore() {
  if (!hasMore.value) return
  const el = messagesContainer.value
  const prevScrollHeight = el?.scrollHeight ?? 0
  const id = sessionId.value
  if (!id) return
  const newOffset = Math.max(0, displayOffset.value - PAGE_SIZE)
  const res = await api.loadChatSession(id, newOffset, displayOffset.value - newOffset)
  if (!res) return
  const prepend = res.messages.map(mapChatMessage)
  messages.value = [...prepend, ...messages.value]
  displayOffset.value = newOffset
  // Restore scroll position so view doesn't jump
  await nextTick()
  if (el) {
    el.scrollTop = el.scrollHeight - prevScrollHeight
  }
}

watch(
  () => route.params.id,
  async (newId, oldId) => {
    // Abort only when navigating away from the session that is currently streaming
    if ((isPlanning.value || isStreaming.value) && newId !== oldId) {
      if (isStreaming.value) abortStream()
      // Fire-and-forget: persist the local messages (including __INTERRUPTED__) to the backend
      if (streamingSessionId.value) {
        api.cancelChatSession(streamingSessionId.value, messages.value).catch(() => {})
      }
    }
    // Save current session state before switching
    if (oldId && Number(oldId) !== Number(newId)) {
      const oldIdNum = Number(oldId)
      if (!isNaN(oldIdNum)) saveToCache(oldIdNum)
    }
    if (newId) {
      await loadSession(Number(newId))
    } else {
      messages.value = []
      totalMessages.value = 0
      displayOffset.value = 0
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

function forceScrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function scrollToBottom() {
  if (!autoScroll.value) return
  forceScrollToBottom()
}

function onContainerScroll() {
  const el = messagesContainer.value
  if (!el) return
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distFromBottom > 80) {
    autoScroll.value = false
  }
}

// Keep scroll pinned to bottom whenever content changes
// Deep watch catches token-by-token content updates inside messages array items
watch(messages, scrollToBottom, { deep: true })
watch([isStreaming, isPlanning], scrollToBottom)

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
  streamAbort.value?.()
  streamAbort.value = null
  if (streamingSessionId.value) {
    const last = messages.value[messages.value.length - 1]
    if (!last || last.content !== '__INTERRUPTED__') {
      messages.value.push({ role: 'assistant', content: '__INTERRUPTED__' })
    }
  }
  isStreaming.value = false
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
  if (!query || isPlanning.value || isStreaming.value) return

  autoScroll.value = true
  inputText.value = ''
  nextTick(() => adjustHeight())
  totalMessages.value += 1
  const userMsg: Message = { role: 'user', content: query }
  messages.value.push(userMsg)

  // If new chat (no session yet), create session immediately so sidebar updates at once
  let currentSessionId = sessionId.value
  if (!currentSessionId) {
    const newSession = await api.createChatSession(query.slice(0, 30))
    currentSessionId = newSession.id
    chatStore.loadSessions()
  }
  streamingSessionId.value = currentSessionId

  // Push assistant placeholder with thinking state = in-progress
  const assistantIdx = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    thinking: {
      steps: [],
      ragContext: [],
      completed: false,
      collapsed: false,
      ragCollapsed: true,
    },
  })

  const history = messages.value
    .filter(m => m.role !== 'user' || m.content !== query)
    .slice(-10)
    .map(m => ({ role: m.role, content: m.content }))

  // ─── Step 1: Plan (SSE streaming steps) ───
  isPlanning.value = true
  let planResult: PlanResponse | null = null

  await new Promise<void>((resolve) => {
    const { promise: planPromise, abort: planAbort } = api.planChatStream(
      {
        query,
        session_id: currentSessionId,
        conversation_history: history,
        qa_meta: qaMeta.value,
      },
      {
        onStep: (step) => {
          const msg = messages.value[assistantIdx]
          if (msg?.thinking) {
            const existing = msg.thinking.steps.find((s: any) => s.node_name === (step as any).node_name && s.status === (step as any).status)
            if (!existing) {
              msg.thinking.steps = [...msg.thinking.steps, step as any]
            }
          }
        },
        onDone: (data) => {
          planResult = data as unknown as PlanResponse
          const msg = messages.value[assistantIdx]
          if (msg?.thinking) {
            msg.thinking.steps = (planResult.step_log ?? [])
            msg.thinking.ragContext = planResult.rag_context ?? []
            msg.thinking.completed = true
            msg.thinking.collapsed = true
          }
          qaMeta.value = planResult.analysis_result.qa_meta
          isPlanning.value = false
          resolve()
        },
        onError: (err) => {
          isPlanning.value = false
          const msg = messages.value[assistantIdx]
          if (msg?.thinking) {
            msg.content = `❌ Plan error: ${err}`
            msg.thinking.completed = true
          } else {
            messages.value.push({ role: 'assistant', content: `❌ Plan error: ${err}` })
          }
          resolve()
        },
      }
    )
    void planPromise
    streamAbort.value = planAbort
  })

  if (!planResult) return
  streamAbort.value = null

  const assistantMsg = messages.value[assistantIdx]

  // ─── Step 2: Stream answer (SSE) ───
  isStreaming.value = true

  try {
    const { promise, abort } = api.streamChat(
      {
        query,
        session_id: currentSessionId,
        conversation_history: history,
        qa_meta: qaMeta.value,
        rag_context: planResult.rag_context,
        step_log: planResult.step_log,
        route: planResult.analysis_result._route,
      },
      {
        onToken: (token: string) => {
          const msg = messages.value[assistantIdx]
          if (msg?.role === 'assistant') {
            msg.content += token
          }
        },
        onDone: async (data) => {
          isStreaming.value = false
          streamingSessionId.value = null
          streamAbort.value = null
          if ((data as any).qa_meta) {
            qaMeta.value = (data as any).qa_meta
          }
          const returnedSessionId = (data as any).session_id
          if (returnedSessionId && !sessionId.value) {
            router.replace(`/chat/${returnedSessionId}`)
          }
          // Update cache so switching back preserves the new messages
          const sid = returnedSessionId ?? sessionId.value
          if (sid) saveToCache(sid)
          if (authStore.isLoggedIn) {
            chatStore.loadSessions()
          }
        },
        onError: async (err) => {
          streamAbort.value = null
          isStreaming.value = false
          streamingSessionId.value = null
          const msg = messages.value[assistantIdx]
          if (msg?.role === 'assistant') {
            msg.content = `❌ Error: ${err}`
          } else {
            messages.value.push({ role: 'assistant', content: `❌ Error: ${err}` })
          }
        },
      }
    )
    streamAbort.value = abort
    await promise
    streamAbort.value = null
  } catch (e: unknown) {
    const msg = messages.value[assistantIdx]
    if (msg?.role === 'assistant') {
      msg.content = `❌ ${(e as Error).message}`
    } else {
      messages.value.push({ role: 'assistant', content: `❌ ${(e as Error).message}` })
    }
    isStreaming.value = false
  }
}

</script>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
