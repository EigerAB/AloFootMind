import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api, type ChatSession } from '@/api'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([])
  const activeSessionId = ref<number | null>(null)

  const isLoading = ref(false)

  const sortedSessions = computed(() =>
    [...sessions.value].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    )
  )

  async function loadSessions() {
    isLoading.value = true
    try {
      sessions.value = await api.getChatSessions().catch(() => [])
    } finally {
      isLoading.value = false
    }
  }

  async function createSession(name?: string): Promise<number> {
    const res = await api.createChatSession(name)
    await loadSessions()
    activeSessionId.value = res.id
    return res.id
  }

  async function renameSession(id: number, name: string) {
    await api.renameChatSession(id, name)
    await loadSessions()
  }

  async function deleteSession(id: number) {
    await api.deleteChatSession(id)
    await loadSessions()
    if (activeSessionId.value === id) activeSessionId.value = null
  }

  function setActiveSession(id: number | null) {
    activeSessionId.value = id
  }

  return {
    sessions,
    activeSessionId,
    isLoading,
    sortedSessions,
    loadSessions,
    createSession,
    renameSession,
    deleteSession,
    setActiveSession,
  }
})
