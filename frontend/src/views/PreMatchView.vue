<template>
  <div class="p-6 max-w-4xl mx-auto">
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-white">Pre-Match Intelligence</h2>
      <p class="text-gray-400 text-sm mt-1">Select two teams to generate a tactical intelligence report</p>
    </div>

    <!-- Team selector -->
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
      <div class="grid md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="block text-xs text-gray-500 mb-1.5">Home Team</label>
          <input
            v-model="homeQuery"
            @input="searchTeams('home')"
            placeholder="Search team..."
            class="w-full bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none"
          />
          <div v-if="homeSuggestions.length" class="mt-1 bg-gray-800 border border-gray-700 rounded-lg overflow-hidden max-h-40 overflow-y-auto">
            <button
              v-for="t in homeSuggestions"
              :key="t.team_id"
              @click="selectTeam('home', t)"
              class="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors"
            >{{ t.team_name }}</button>
          </div>
          <div v-if="homeTeam" class="mt-2 px-3 py-1.5 bg-green-900/30 border border-green-800/50 rounded-lg text-sm text-green-400">
            ✓ {{ homeTeam.team_name }}
          </div>
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5">Away Team</label>
          <input
            v-model="awayQuery"
            @input="searchTeams('away')"
            placeholder="Search team..."
            class="w-full bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none"
          />
          <div v-if="awaySuggestions.length" class="mt-1 bg-gray-800 border border-gray-700 rounded-lg overflow-hidden max-h-40 overflow-y-auto">
            <button
              v-for="t in awaySuggestions"
              :key="t.team_id"
              @click="selectTeam('away', t)"
              class="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors"
            >{{ t.team_name }}</button>
          </div>
          <div v-if="awayTeam" class="mt-2 px-3 py-1.5 bg-blue-900/30 border border-blue-800/50 rounded-lg text-sm text-blue-400">
            ✓ {{ awayTeam.team_name }}
          </div>
        </div>
      </div>

      <button
        @click="generateReport"
        :disabled="!homeTeam || !awayTeam || isRunning"
        class="w-full py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white font-semibold rounded-xl transition-colors"
      >
        🔍 Generate Intelligence Report
      </button>
    </div>

    <!-- Agent Viewer -->
    <AgentViewer v-if="stepLog.length || isRunning" :steps="stepLog" :is-running="isRunning" :error="agentError" class="mb-6" />

    <!-- Report -->
    <ReportViewer v-if="report" :markdown="report" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api, type Team } from '@/api'
import { useSseStream } from '@/composables/useSseStream'
import AgentViewer from '@/components/AgentViewer.vue'
import ReportViewer from '@/components/ReportViewer.vue'

const homeQuery = ref('')
const awayQuery = ref('')
const homeSuggestions = ref<Team[]>([])
const awaySuggestions = ref<Team[]>([])
const homeTeam = ref<Team | null>(null)
const awayTeam = ref<Team | null>(null)
const isRunning = ref(false)
const stepLog = ref<any[]>([])
const report = ref<string | null>(null)
const agentError = ref<string | null>(null)

const { start: startSse, stop: stopSse } = useSseStream()

let searchTimer: ReturnType<typeof setTimeout>

async function searchTeams(side: 'home' | 'away') {
  const query = side === 'home' ? homeQuery.value : awayQuery.value
  if (query.length < 2) {
    if (side === 'home') homeSuggestions.value = []
    else awaySuggestions.value = []
    return
  }
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const results = await api.getTeams(query).catch(() => [])
    if (side === 'home') homeSuggestions.value = results.slice(0, 8)
    else awaySuggestions.value = results.slice(0, 8)
  }, 300)
}

function selectTeam(side: 'home' | 'away', team: Team) {
  if (side === 'home') {
    homeTeam.value = team
    homeQuery.value = team.team_name
    homeSuggestions.value = []
  } else {
    awayTeam.value = team
    awayQuery.value = team.team_name
    awaySuggestions.value = []
  }
}

async function generateReport() {
  if (!homeTeam.value || !awayTeam.value) return
  stepLog.value = []
  report.value = null
  agentError.value = null
  isRunning.value = true

  try {
    const res = await api.triggerPreMatch(homeTeam.value.team_id, awayTeam.value.team_id)
    startSse(`/api/tasks/${res.task_id}/stream`, {
      onEvent: (data) => {
        stepLog.value = [...stepLog.value, data]
      },
      onDone: async (_data) => {
        isRunning.value = false
        const result = await api.getTaskStatus(res.task_id)
        if (result.has_result) {
          const r = await fetch(`/api/tasks/${res.task_id}/result`).then(r => r.json()).catch(() => null)
          if (r?.result) report.value = r.result
        }
        stopSse()
      },
      onError: (err) => {
        isRunning.value = false
        agentError.value = err
        stopSse()
      },
    })
  } catch (e: unknown) {
    isRunning.value = false
    agentError.value = (e as Error).message
  }
}
</script>
