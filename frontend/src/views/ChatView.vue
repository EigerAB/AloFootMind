<template>
  <div class="flex flex-col h-screen">
    <!-- Header -->
    <div class="bg-gray-900 border-b border-gray-800 px-6 py-4 shrink-0">
      <h2 class="text-lg font-bold text-white">{{ t('chat.title') }}</h2>
      <p class="text-xs text-gray-500 mt-0.5">{{ t('chat.subtitle') }}</p>
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
        <!-- User message -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="bg-green-800 text-white text-sm rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg">
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
              class="bg-gray-900 border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm prose-report max-w-3xl"
              v-html="renderMarkdown(msg.content)"
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
      <div class="flex gap-3 max-w-4xl mx-auto">
        <input
          v-model="inputText"
          @keydown.enter.prevent="sendMessage()"
          :disabled="isStreaming"
          :placeholder="t('chat.inputPlaceholder')"
          class="flex-1 bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-xl px-4 py-3 focus:ring-1 focus:ring-green-500 focus:outline-none disabled:opacity-50"
        />
        <button
          @click="sendMessage()"
          :disabled="!inputText.trim() || isStreaming"
          class="px-5 py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white rounded-xl transition-colors font-medium"
        >
          {{ t('chat.sendBtn') }}
        </button>
      </div>
    </div>
    <AuthModal v-model:visible="showAuthModal" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useSseStream } from '@/composables/useSseStream'
import { useMarkdown } from '@/composables/useMarkdown'
import AuthModal from '@/components/AuthModal.vue'
const { t, tm } = useI18n()
const authStore = useAuthStore()
const showAuthModal = ref(false)
const localeSuggestions = computed(() => tm('chat.suggestions') as string[])

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: { text: string; collection: string }[]
}

const messages = ref<Message[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamBuffer = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

// qa_meta for cross-turn football-intent tracking
const qaMeta = ref<{ football_intent_count: number; generic_turn_count: number }>({
  football_intent_count: 0,
  generic_turn_count: 0,
})

const { post: postSse } = useSseStream()
const { render: renderMarkdown } = useMarkdown()

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function sendMessage(text?: string) {
  if (!authStore.isLoggedIn) {
    showAuthModal.value = true
    return
  }
  const query = (text ?? inputText.value).trim()
  if (!query || isStreaming.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: query })
  await scrollToBottom()

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
        session_id: 'ui-session',
        qa_meta: qaMeta.value,
      },
      {
        onToken: (token: string) => {
          streamBuffer.value += token
          scrollToBottom()
        },
        onEvent: (data) => {
          if ((data as any).token) {
            streamBuffer.value += (data as any).token
            scrollToBottom()
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
          streamBuffer.value = ''
          isStreaming.value = false
          scrollToBottom()
        },
        onError: (err) => {
          messages.value.push({
            role: 'assistant',
            content: `❌ Error: ${err}`,
          })
          streamBuffer.value = ''
          isStreaming.value = false
          scrollToBottom()
        },
      }
    )
  } catch (e: unknown) {
    messages.value.push({ role: 'assistant', content: `❌ ${(e as Error).message}` })
    isStreaming.value = false
  }
}

</script>
