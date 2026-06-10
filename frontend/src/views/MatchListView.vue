<template>
  <div class="flex flex-col h-full">
    <!-- Fixed header: title + filters -->
    <div class="px-6 pt-6 pb-4 shrink-0">
      <div class="mb-4 max-w-6xl mx-auto">
        <h2 class="text-2xl font-bold text-white">{{ t('matches.title') }}</h2>
        <p class="text-gray-400 text-sm mt-1">{{ t('matches.subtitle') }}</p>
      </div>
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-wrap gap-3 max-w-6xl mx-auto">
        <SearchableSelect
          v-model="selectedCompetition"
          :options="competitionOptions"
          :null-label="t('matches.allCompetitions')"
          track-key="key"
          display-key="label"
          :placeholder="t('matches.allCompetitions')"
          :searchable="false"
          @select="onCompetitionSelect"
          class="w-56"
        />
        <input
          v-model="teamFilter"
          @keyup.enter="filterByTeam"
          :placeholder="t('matches.filterPlaceholder')"
          class="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-green-500 focus:outline-none w-48"
        />
        <button
          @click="filterByTeam"
          class="px-4 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition-colors"
        >
          {{ t('matches.searchBtn') }}
        </button>
      </div>
    </div>

    <!-- Table area -->
    <div class="flex-1 px-6 pb-4 min-h-0">
      <div class="max-w-6xl mx-auto h-full flex flex-col">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-12 text-gray-500">
          <div class="text-3xl mb-2 animate-spin inline-block">⚽</div>
          <p>{{ t('matches.loading') }}</p>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="bg-red-950/40 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
          {{ error }}
        </div>

        <!-- Table -->
        <div v-else class="flex flex-col h-full">
          <div class="flex-1 overflow-auto border border-gray-800 rounded-t-xl">
            <table class="w-full text-sm text-left text-gray-300">
              <thead class="text-xs text-gray-400 uppercase bg-gray-900 sticky top-0 z-10">
                <tr>
                  <th class="px-4 py-3">{{ t('matches.colDate') }}</th>
                  <th class="px-4 py-3">{{ t('matches.colCompetition') }}</th>
                  <th class="px-4 py-3">{{ t('matches.colSeason') }}</th>
                  <th class="px-4 py-3 text-center">{{ t('matches.colWeek') }}</th>
                  <th class="px-4 py-3 text-right">{{ t('matches.colHomeTeam') }}</th>
                  <th class="px-4 py-3 text-center">{{ t('matches.colHomeFormation') }}</th>
                  <th class="px-4 py-3 text-center">{{ t('matches.colScore') }}</th>
                  <th class="px-4 py-3 text-center">{{ t('matches.colAwayFormation') }}</th>
                  <th class="px-4 py-3">{{ t('matches.colAwayTeam') }}</th>
                  <th class="px-4 py-3 text-center">{{ t('matches.colReport') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in matches"
                  :key="m.match_id"
                  @click="$router.push(`/matches/${m.match_id}`)"
                  class="bg-gray-900/50 border-b border-gray-800 hover:bg-gray-800 cursor-pointer transition-colors"
                >
                  <td class="px-4 py-3 whitespace-nowrap">{{ m.match_date }}</td>
                  <td class="px-4 py-3 whitespace-nowrap">{{ m.competition_name }}</td>
                  <td class="px-4 py-3 whitespace-nowrap">{{ m.season_name }}</td>
                  <td class="px-4 py-3 text-center">{{ m.match_week ?? '—' }}</td>
                  <td class="px-4 py-3 text-right font-semibold text-white">{{ m.home_team_name }}</td>
                  <td class="px-4 py-3 text-center text-gray-500">{{ m.home_formation ? formatFormation(m.home_formation) : '—' }}</td>
                  <td class="px-4 py-3 text-center font-bold text-white font-mono">
                    {{ m.home_score }} – {{ m.away_score }}
                  </td>
                  <td class="px-4 py-3 text-center text-gray-500">{{ m.away_formation ? formatFormation(m.away_formation) : '—' }}</td>
                  <td class="px-4 py-3 font-semibold text-white">{{ m.away_team_name }}</td>
                  <td class="px-4 py-3 text-center">
                    <span v-if="m.has_report" class="text-green-500">✓</span>
                    <span v-else class="text-gray-600">—</span>
                  </td>
                </tr>
                <tr v-if="matches.length === 0">
                  <td colspan="10" class="px-4 py-12 text-center text-gray-600">
                    {{ t('matches.noResults') }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div class="shrink-0 bg-gray-900 border border-t-0 border-gray-800 rounded-b-xl px-4 py-3 flex items-center justify-between">
            <div class="flex items-center gap-2 text-sm text-gray-400">
              <span>{{ t('matches.pageSize') }}</span>
              <select
                v-model="pageSize"
                @change="onPageSizeChange"
                class="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-2 py-1 focus:ring-1 focus:ring-green-500 focus:outline-none"
              >
                <option :value="10">10</option>
                <option :value="20">20</option>
                <option :value="50">50</option>
              </select>
              <span>{{ t('matches.total', { total }) }}</span>
            </div>
            <div class="flex items-center gap-2">
              <button
                @click="goToPage(currentPage - 1)"
                :disabled="currentPage <= 1"
                class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 text-sm rounded-lg transition-colors"
              >
                {{ t('matches.prev') }}
              </button>
              <span class="text-sm text-gray-400 px-2">
                {{ currentPage }} / {{ totalPages }}
              </span>
              <button
                @click="goToPage(currentPage + 1)"
                :disabled="currentPage >= totalPages"
                class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-300 text-sm rounded-lg transition-colors"
              >
                {{ t('matches.next') }}
              </button>
              <div class="flex items-center gap-1 ml-2">
                <input
                  v-model.number="jumpPage"
                  @keyup.enter="jumpToPage"
                  type="number"
                  min="1"
                  :max="totalPages"
                  class="bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-2 py-1 w-14 text-center focus:ring-1 focus:ring-green-500 focus:outline-none"
                />
                <button
                  @click="jumpToPage"
                  class="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white text-sm rounded-lg transition-colors"
                >
                  {{ t('matches.jump') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, type Competition, type Match } from '@/api'
import SearchableSelect from '@/components/SearchableSelect.vue'

const { t } = useI18n()
const $router = useRouter()

const competitions = ref<Competition[]>([])
const matches = ref<Match[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const selectedCompetition = ref<{ key: string; label: string; competition_id: number; season_id: number } | null>(null)
const teamFilter = ref('')
const selectedTeamId = ref<number | undefined>()
const currentPage = ref(1)
const pageSize = ref(50)
const jumpPage = ref(1)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

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
  if (!selectedCompetition.value) return { competition_id: undefined, season_id: undefined }
  return { competition_id: selectedCompetition.value.competition_id, season_id: selectedCompetition.value.season_id }
}

function onCompetitionSelect() {
  currentPage.value = 1
  jumpPage.value = 1
  loadMatches()
}

async function filterByTeam() {
  if (!teamFilter.value.trim()) {
    selectedTeamId.value = undefined
    currentPage.value = 1
    jumpPage.value = 1
    await loadMatches()
    return
  }
  const teams = await api.getTeams(teamFilter.value)
  if (teams.length > 0) {
    selectedTeamId.value = teams[0].team_id
    currentPage.value = 1
    jumpPage.value = 1
    await loadMatches()
  }
}

async function loadMatches() {
  loading.value = true
  error.value = null
  try {
    const { competition_id, season_id } = parseKey()
    const offset = (currentPage.value - 1) * pageSize.value
    const res = await api.getMatches({
      competition_id,
      season_id,
      team_id: selectedTeamId.value,
      limit: pageSize.value,
      offset,
    })
    matches.value = res.items
    total.value = res.total
  } catch (e: unknown) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value) return
  currentPage.value = page
  loadMatches()
}

function onPageSizeChange() {
  currentPage.value = 1
  jumpPage.value = 1
  loadMatches()
}

function jumpToPage() {
  let page = Math.round(jumpPage.value)
  if (Number.isNaN(page)) page = 1
  page = Math.max(1, Math.min(page, totalPages.value))
  jumpPage.value = page
  goToPage(page)
}

function formatFormation(f: number) {
  return String(f)
    .split('')
    .join('-')
    .trim() || String(f)
}

onMounted(async () => {
  competitions.value = await api.getCompetitions().catch(() => [])
  await loadMatches()
})
</script>

<style scoped>
input[type="number"]::-webkit-outer-spin-button,
input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
}
</style>
