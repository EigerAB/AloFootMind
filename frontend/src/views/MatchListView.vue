<template>
  <div class="flex flex-col h-full">
    <!-- Fixed header: title + filters -->
    <div class="px-6 pt-6 pb-4 shrink-0">
      <div class="mb-4 max-w-6xl mx-auto">
        <h2 class="text-2xl font-bold text-white">{{ t('matches.title') }}</h2>
        <p class="text-gray-400 text-sm mt-1">{{ t('matches.subtitle') }}</p>
      </div>
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-wrap gap-3 max-w-6xl mx-auto">
        <select
          v-model="selectedCompetitionKey"
          class="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none"
        >
          <option value="">{{ t('matches.allCompetitions') }}</option>
          <option v-for="c in competitionOptions" :key="c.key" :value="c.key">
            {{ c.label }}
          </option>
        </select>
        <input
          v-model="teamFilter"
          @keyup.enter="filterByTeam"
          :placeholder="t('matches.filterPlaceholder')"
          class="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none w-48"
        />
        <button
          @click="loadMatches"
          class="px-4 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition-colors"
        >
          {{ t('matches.searchBtn') }}
        </button>
      </div>
    </div>

    <!-- Scrollable match list -->
    <div class="flex-1 overflow-y-auto px-6 pb-6">
      <div class="max-w-6xl mx-auto">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-12 text-gray-500">
          <div class="text-3xl mb-2 animate-spin inline-block">⚽</div>
          <p>{{ t('matches.loading') }}</p>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="bg-red-950/40 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
          {{ error }}
        </div>

        <!-- Match cards -->
        <div v-else class="grid gap-3">
          <RouterLink
            v-for="m in matches"
            :key="m.match_id"
            :to="`/matches/${m.match_id}`"
            class="block bg-gray-900 border border-gray-800 hover:border-green-800 rounded-xl p-4 transition-all group"
          >
            <div class="flex items-center justify-between gap-4">
              <div class="flex-1 text-right">
                <div class="font-semibold text-white group-hover:text-green-300 transition-colors">
                  {{ m.home_team_name }}
                </div>
                <div class="text-xs text-gray-500 mt-0.5">
                  {{ m.home_formation ? formatFormation(m.home_formation) : '—' }}
                </div>
              </div>

              <div class="shrink-0 text-center px-4">
                <div class="text-2xl font-bold text-white font-mono">
                  {{ m.home_score }} <span class="text-gray-500">–</span> {{ m.away_score }}
                </div>
                <div class="text-xs text-gray-600 mt-0.5">{{ m.match_date }}</div>
              </div>

              <div class="flex-1 text-left">
                <div class="font-semibold text-white group-hover:text-green-300 transition-colors">
                  {{ m.away_team_name }}
                </div>
                <div class="text-xs text-gray-500 mt-0.5">
                  {{ m.away_formation ? formatFormation(m.away_formation) : '—' }}
                </div>
              </div>

              <div class="shrink-0 text-right hidden sm:block">
                <div class="text-xs text-gray-500">{{ m.competition_name }}</div>
                <div class="text-xs text-gray-600">{{ m.season_name }}</div>
                <div class="text-xs text-gray-700 mt-0.5">MW {{ m.match_week ?? '—' }}</div>
              </div>
            </div>
          </RouterLink>

          <div v-if="matches.length === 0 && !loading" class="text-center py-12 text-gray-600">
            {{ t('matches.noResults') }}
          </div>
        </div>

        <!-- Load more -->
        <div v-if="matches.length > 0 && matches.length % 50 === 0" class="mt-6 text-center">
          <button
            @click="loadMore"
            :disabled="loadingMore"
            class="px-6 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors disabled:opacity-50"
          >
            {{ loadingMore ? t('matches.loadingMore') : t('matches.loadMore') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, type Competition, type Match } from '@/api'
const { t } = useI18n()

const competitions = ref<Competition[]>([])
const matches = ref<Match[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref<string | null>(null)
const selectedCompetitionKey = ref('')
const teamFilter = ref('')
const selectedTeamId = ref<number | undefined>()
const offset = ref(0)

const competitionOptions = computed(() => {
  const seen = new Set<string>()
  return competitions.value
    .filter(c => {
      const k = `${c.competition_id}:${c.season_id}`
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
    .map(c => ({
      key: `${c.competition_id}:${c.season_id}`,
      label: `${c.competition_name} ${c.season_name}`,
      competition_id: c.competition_id,
      season_id: c.season_id,
    }))
})

function parseKey() {
  if (!selectedCompetitionKey.value) return { competition_id: undefined, season_id: undefined }
  const [cid, sid] = selectedCompetitionKey.value.split(':').map(Number)
  return { competition_id: cid, season_id: sid }
}

async function filterByTeam() {
  if (!teamFilter.value.trim()) {
    selectedTeamId.value = undefined
    loadMatches()
    return
  }
  const teams = await api.getTeams(teamFilter.value)
  if (teams.length > 0) {
    selectedTeamId.value = teams[0].team_id
    loadMatches()
  }
}

async function loadMatches() {
  loading.value = true
  error.value = null
  offset.value = 0
  try {
    const { competition_id, season_id } = parseKey()
    matches.value = await api.getMatches({
      competition_id,
      season_id,
      team_id: selectedTeamId.value,
      limit: 50,
      offset: 0,
    })
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  offset.value += 50
  try {
    const { competition_id, season_id } = parseKey()
    const more = await api.getMatches({
      competition_id,
      season_id,
      team_id: selectedTeamId.value,
      limit: 50,
      offset: offset.value,
    })
    matches.value = [...matches.value, ...more]
  } finally {
    loadingMore.value = false
  }
}

function formatFormation(f: number) {
  return String(f)
    .split('')
    .join('-')
    .replace(/^(\d)-/, '$1 ')
    .trim() || String(f)
}

onMounted(async () => {
  competitions.value = await api.getCompetitions().catch(() => [])
  loadMatches()
})
</script>
