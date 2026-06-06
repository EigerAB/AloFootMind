<template>
  <div class="p-6 max-w-4xl mx-auto">
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-white">{{ t('preMatch.title') }}</h2>
      <p class="text-gray-400 text-sm mt-1">{{ t('preMatch.subtitle') }}</p>
    </div>

    <!-- Team selector -->
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
      <div class="grid md:grid-cols-2 gap-4 mb-4">
        <!-- Home -->
        <div>
          <label class="block text-xs text-gray-500 mb-1.5">{{ t('preMatch.competition') }}</label>
          <select
            v-model="homeCompId"
            @change="onCompetitionChange('home')"
            class="w-full bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none mb-3"
          >
            <option :value="null" disabled>{{ t('preMatch.selectCompetition') }}</option>
            <option v-for="c in hierarchy" :key="c.competition_id" :value="c.competition_id">
              {{ c.competition_name }}
            </option>
          </select>

          <label class="block text-xs text-gray-500 mb-1.5">{{ t('preMatch.homeTeam') }}</label>
          <SearchableSelect
            v-model="homeTeam"
            :options="homeFilteredTeams"
            :disabled="!homeCompId"
            :placeholder="t('preMatch.searchPlaceholder')"
            track-key="team_id"
            display-key="team_name"
            @select="onTeamSelect('home')"
          />
        </div>

        <!-- Away -->
        <div>
          <label class="block text-xs text-gray-500 mb-1.5">{{ t('preMatch.competition') }}</label>
          <select
            v-model="awayCompId"
            @change="onCompetitionChange('away')"
            class="w-full bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none mb-3"
          >
            <option :value="null" disabled>{{ t('preMatch.selectCompetition') }}</option>
            <option v-for="c in hierarchy" :key="c.competition_id" :value="c.competition_id">
              {{ c.competition_name }}
            </option>
          </select>

          <label class="block text-xs text-gray-500 mb-1.5">{{ t('preMatch.awayTeam') }}</label>
          <SearchableSelect
            v-model="awayTeam"
            :options="awayFilteredTeams"
            :disabled="!awayCompId"
            :placeholder="t('preMatch.searchPlaceholder')"
            track-key="team_id"
            display-key="team_name"
            @select="onTeamSelect('away')"
          />
        </div>
      </div>

      <button
        @click="generateReport"
        :disabled="!homeTeam || !awayTeam || isRunning"
        class="w-full py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white font-semibold rounded-xl transition-colors"
      >
        {{ t('preMatch.generateBtn') }}
      </button>
    </div>

    <!-- Agent Viewer -->
    <AgentViewer v-if="stepLog.length || isRunning" :steps="stepLog" :is-running="isRunning" :error="agentError" class="mb-6" />

    <!-- Report -->
    <ReportViewer v-if="report" :markdown="report" />

    <!-- Same-team error dialog -->
    <Teleport to="body">
      <div
        v-if="showSameTeamError"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showSameTeamError = false"
      >
        <div class="bg-gray-900 border border-red-800/60 rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl">
          <div class="flex items-center gap-3 mb-3">
            <span class="text-2xl">⚠️</span>
            <h3 class="text-white font-semibold text-base">{{ t('preMatch.sameTeamTitle') }}</h3>
          </div>
          <p class="text-gray-400 text-sm mb-5">{{ t('preMatch.sameTeamMsg') }}</p>
          <button
            @click="showSameTeamError = false"
            class="w-full py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {{ t('preMatch.sameTeamClose') }}
          </button>
        </div>
      </div>
    </Teleport>
    <AuthModal v-model:visible="showAuthModal" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Team, type CompetitionWithTeams } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useSseStream } from '@/composables/useSseStream'
import AgentViewer from '@/components/AgentViewer.vue'
import ReportViewer from '@/components/ReportViewer.vue'
import AuthModal from '@/components/AuthModal.vue'
import SearchableSelect from '@/components/SearchableSelect.vue'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const showAuthModal = ref(false)

const hierarchy = ref<CompetitionWithTeams[]>([])

const homeCompId = ref<number | null>(null)
const homeTeam = ref<Team | null>(null)

const awayCompId = ref<number | null>(null)
const awayTeam = ref<Team | null>(null)

const isRunning = ref(false)
const stepLog = ref<any[]>([])
const report = ref<string | null>(null)
const agentError = ref<string | null>(null)
const showSameTeamError = ref(false)

const { start: startSse, stop: stopSse } = useSseStream()

const homeFilteredTeams = computed(() => {
  const comp = hierarchy.value.find(c => c.competition_id === homeCompId.value)
  return comp?.teams ?? []
})

const awayFilteredTeams = computed(() => {
  const comp = hierarchy.value.find(c => c.competition_id === awayCompId.value)
  return comp?.teams ?? []
})

onMounted(async () => {
  hierarchy.value = await api.getTeamsHierarchy().catch(() => [])
})

function onCompetitionChange(side: 'home' | 'away') {
  if (side === 'home') {
    homeTeam.value = null
  } else {
    awayTeam.value = null
  }
}

function onTeamSelect(_side: 'home' | 'away') {
  // v-model handles the value; this hook can be used for side-effects if needed
}

async function generateReport() {
  if (!authStore.isLoggedIn) {
    showAuthModal.value = true
    return
  }
  if (!homeTeam.value || !awayTeam.value) return
  if (homeTeam.value.team_id === awayTeam.value.team_id) {
    showSameTeamError.value = true
    return
  }
  stepLog.value = []
  report.value = null
  agentError.value = null
  isRunning.value = true

  try {
    const res = await api.triggerPreMatch(homeTeam.value.team_id, awayTeam.value.team_id, locale.value)
    startSse(`/api/tasks/${res.task_id}/stream`, {
      onEvent: (data) => {
        stepLog.value = [...stepLog.value, data]
      },
      onDone: async (_data) => {
        isRunning.value = false
        const result = await api.getTaskStatus(res.task_id)
        if (result.has_result) {
          const r = await api.getTaskResult(res.task_id).catch(() => null)
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
