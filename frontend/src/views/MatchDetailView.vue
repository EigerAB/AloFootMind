<template>
  <div class="p-6 max-w-5xl mx-auto">
    <!-- Back -->
    <RouterLink to="/matches" class="text-sm text-gray-500 hover:text-gray-300 flex items-center gap-1 mb-5">
      {{ t('matchDetail.backToMatches') }}
    </RouterLink>

    <!-- Loading state -->
    <div v-if="loading" class="text-center py-16 text-gray-500">
      <div class="text-3xl animate-spin inline-block">⚽</div>
      <p class="mt-2">{{ t('matchDetail.loading') }}</p>
    </div>

    <template v-else-if="match">
      <!-- Score header -->
      <div class="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-6 text-center">
        <div class="text-xs text-gray-500 mb-3">{{ match.competition_name }} · {{ match.season_name }}</div>
        <div class="flex items-center justify-between gap-6">
          <div class="flex-1">
            <div class="text-xl font-bold text-white">{{ match.home_team_name }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ match.home_manager ?? t('matchDetail.managerNA') }}</div>
            <div class="text-sm text-gray-500 mt-1">{{ t('matchDetail.formation', { f: match.home_formation ?? '—' }) }}</div>
          </div>
          <div class="shrink-0">
            <div class="text-5xl font-black text-white font-mono">
              {{ match.home_score }}<span class="text-gray-600 mx-2">–</span>{{ match.away_score }}
            </div>
            <div class="text-xs text-gray-600 mt-2">{{ match.match_date }}</div>
            <div v-if="match.stadium_name" class="text-xs text-gray-600">{{ match.stadium_name }}</div>
          </div>
          <div class="flex-1 text-right">
            <div class="text-xl font-bold text-white">{{ match.away_team_name }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ match.away_manager ?? t('matchDetail.managerNA') }}</div>
            <div class="text-sm text-gray-500 mt-1">{{ t('matchDetail.formation', { f: match.away_formation ?? '—' }) }}</div>
          </div>
        </div>
      </div>

      <!-- Stats grid -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard :label="t('matchDetail.stats.shots')" :home="match.home_shots" :away="match.away_shots" />
        <StatCard :label="t('matchDetail.stats.onTarget')" :home="match.home_shots_on_target" :away="match.away_shots_on_target" />
        <StatCard :label="t('matchDetail.stats.passes')" :home="match.home_passes" :away="match.away_passes" />
        <StatCard :label="t('matchDetail.stats.fouls')" :home="match.home_fouls" :away="match.away_fouls" />
      </div>

      <!-- Key Events -->
      <div v-if="match.key_events?.length" class="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6">
        <h3 class="text-sm font-semibold text-gray-300 mb-3">{{ t('matchDetail.keyEvents') }}</h3>
        <div class="space-y-1.5">
          <div
            v-for="(ev, i) in match.key_events"
            :key="i"
            class="flex items-center gap-3 text-sm"
          >
            <span class="text-gray-600 font-mono w-10 shrink-0">{{ ev.minute }}'</span>
            <span :class="ev.type === 'Goal' ? 'text-green-400' : ev.type.includes('Red') ? 'text-red-400' : 'text-yellow-400'">
              {{ ev.type === 'Goal' ? '⚽' : ev.type.includes('Red') ? '🟥' : '🟨' }}
            </span>
            <span class="text-gray-300">{{ ev.player }}</span>
            <span class="text-gray-600 text-xs">{{ ev.type }}</span>
          </div>
        </div>
      </div>

      <!-- Analyze button + Agent viewer -->
      <div class="mb-6">
        <button
          v-if="!taskId && !report"
          @click="triggerAnalysis"
          :disabled="analyzing"
          class="w-full py-3 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors"
        >
          {{ analyzing ? t('matchDetail.analyzing') : t('matchDetail.analyzeBtn') }}
        </button>
      </div>

      <div v-if="statusMsg" class="mb-4 px-4 py-2 bg-green-900/40 border border-green-700 rounded-lg text-sm text-green-300">
        {{ statusMsg }}
      </div>
      <AgentViewer v-if="stepLog.length || isRunning || agentError" :steps="stepLog" :is-running="isRunning" :error="agentError" class="mb-6" />

      <ReportViewer v-if="report" :markdown="report" />

      <!-- Lineups -->
      <div v-if="match.lineups?.length" class="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h3 class="text-sm font-semibold text-gray-300 mb-3">{{ t('matchDetail.lineups') }}</h3>
        <div class="grid md:grid-cols-2 gap-4">
          <div v-for="teamId in [match.home_team_id, match.away_team_id]" :key="teamId">
            <div class="text-xs font-semibold text-gray-500 mb-2">
              {{ teamId === match.home_team_id ? match.home_team_name : match.away_team_name }}
            </div>
            <div class="space-y-1">
              <div
                v-for="p in match.lineups.filter(l => l.team_id === teamId)"
                :key="p.player_id"
                class="flex items-center gap-2 text-sm text-gray-400"
              >
                <span class="w-6 text-center text-xs text-gray-600 font-mono">{{ p.jersey_number ?? '—' }}</span>
                <span>{{ p.player_name }}</span>
                <span v-if="p.position_name" class="text-xs text-gray-600">{{ p.position_name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, type MatchDetail } from '@/api'
import { useSseStream } from '@/composables/useSseStream'
import AgentViewer from '@/components/AgentViewer.vue'
import ReportViewer from '@/components/ReportViewer.vue'

const { t, locale } = useI18n()

const StatCard = {
  props: ['label', 'home', 'away'],
  template: `
    <div class="bg-gray-800 rounded-xl p-3 text-center">
      <div class="text-xs text-gray-500 mb-2">{{ label }}</div>
      <div class="flex justify-between items-center">
        <span class="text-white font-bold">{{ home }}</span>
        <span class="text-gray-600 text-xs">vs</span>
        <span class="text-white font-bold">{{ away }}</span>
      </div>
    </div>
  `,
}

const route = useRoute()
const match = ref<MatchDetail | null>(null)
const loading = ref(true)
const analyzing = ref(false)
const taskId = ref<string | null>(null)
const isRunning = ref(false)
const stepLog = ref<any[]>([])
const report = ref<string | null>(null)
const agentError = ref<string | null>(null)
const statusMsg = ref<string | null>(null)

const { start: startSse, stop: stopSse } = useSseStream()

onMounted(async () => {
  const id = Number(route.params.id)
  try {
    match.value = await api.getMatch(id)
    const existingReport = await api.getMatchReport(id, locale.value).catch(() => null)
    if (existingReport) {
      report.value = existingReport.report_markdown
    }
  } finally {
    loading.value = false
  }
})

async function triggerAnalysis() {
  analyzing.value = true
  agentError.value = null
  try {
    const res = await api.triggerAnalysis(Number(route.params.id), locale.value)
    if (res.status === 'already_done') {
      const r = await api.getMatchReport(Number(route.params.id), locale.value).catch(() => null)
      if (r) {
        report.value = r.report_markdown
        statusMsg.value = t('matchDetail.alreadyDone')
      } else {
        agentError.value = t('matchDetail.reportFetchFailed', '报告获取失败，请刷新重试')
      }
      return
    }
    taskId.value = res.task_id
    isRunning.value = true
    startSse(`/api/tasks/${res.task_id}/stream`, {
      onEvent: (data) => {
        stepLog.value = [...stepLog.value, data]
      },
      onDone: async () => {
        isRunning.value = false
        const r = await api.getMatchReport(Number(route.params.id), locale.value).catch(() => null)
        if (r) report.value = r.report_markdown
        stopSse()
      },
      onError: (err) => {
        isRunning.value = false
        agentError.value = err
        stopSse()
      },
    })
  } catch (e: unknown) {
    agentError.value = (e as Error).message
  } finally {
    analyzing.value = false
  }
}
</script>
