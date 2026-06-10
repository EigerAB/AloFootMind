<template>
  <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
    <h3 class="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse" v-if="isRunning"></span>
      <span class="w-2 h-2 rounded-full bg-gray-500" v-else></span>
      {{ t('agent.title') }}
    </h3>

    <div v-if="mergedNodes.length === 0" class="text-sm text-gray-600 italic py-2">
      {{ t('agent.waiting') }}
    </div>

    <div class="space-y-2">
      <div
        v-for="node in mergedNodes"
        :key="node.node_name"
        class="rounded-lg border text-sm transition-all duration-300"
        :class="nodeClass(node.displayStatus)"
      >
        <!-- Main row -->
        <div class="flex items-center gap-3 p-2.5">
          <!-- Icon -->
          <span class="shrink-0 w-5 text-center">
            <span v-if="node.displayStatus === 'started'" class="inline-block w-4 h-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></span>
            <span v-else-if="node.displayStatus === 'completed'" class="text-green-400">✓</span>
            <span v-else-if="node.displayStatus === 'error'" class="text-red-400">✕</span>
            <span v-else class="text-gray-500">○</span>
          </span>

          <!-- Name + summary -->
          <div class="flex-1 min-w-0">
            <div class="font-medium text-xs" :class="nodeNameClass(node.displayStatus)">
              {{ translateNode(node.node_name) }}
            </div>
            <div class="text-gray-400 text-xs mt-0.5 truncate">{{ node.summary }}</div>
          </div>

          <!-- Time -->
          <div class="text-xs text-gray-600 shrink-0 mr-1">
            {{ formatTime(node.timestamp) }}
          </div>

          <!-- Expand button for nodes with data -->
          <button
            v-if="node.data && node.displayStatus === 'completed'"
            @click="toggleExpand(node.node_name)"
            class="shrink-0 text-xs text-gray-500 hover:text-gray-300 transition-colors px-1.5 py-0.5 rounded border border-gray-700 hover:border-gray-500"
          >
            {{ expanded.has(node.node_name) ? t('agent.collapse') : t('agent.expand') }}
          </button>
        </div>

        <!-- Expandable data section -->
        <div
          v-if="node.data && expanded.has(node.node_name)"
          class="border-t border-gray-700/50 mx-2.5 mb-2.5 pt-2"
        >
          <!-- H2H matches -->
          <template v-if="node.node_name === 'fetch_team_history' && node.data.h2h_matches">
            <div class="text-xs text-gray-500 mb-1.5 font-medium">{{ t('agent.h2hTitle') }}</div>
            <div v-if="node.data.h2h_matches.length === 0" class="text-xs text-gray-600 italic">{{ t('agent.h2hNoData') }}</div>
            <div v-else class="space-y-1">
              <div
                v-for="(m, i) in node.data.h2h_matches"
                :key="i"
                class="flex items-center justify-between text-xs bg-gray-800/60 rounded px-2.5 py-1.5"
              >
                <span class="text-gray-400 w-20 shrink-0">{{ m.match_date?.slice(0, 10) }}</span>
                <span class="text-white font-mono font-semibold">
                  {{ m.home_name }} <span class="text-green-400">{{ m.home_score }}–{{ m.away_score }}</span> {{ m.away_name }}
                </span>
                <span class="text-gray-600 shrink-0">{{ m.home_formation }}|{{ m.away_formation }}</span>
              </div>
            </div>
          </template>

          <!-- RAG segments -->
          <template v-if="node.node_name === 'rag_retrieval' && node.data.segments">
            <div class="text-xs text-gray-500 mb-1.5 font-medium">{{ t('agent.ragTitle') }}</div>
            <div v-if="node.data.segments.length === 0" class="text-xs text-gray-600 italic">{{ t('agent.ragNoData') }}</div>
            <div v-else class="space-y-1.5">
              <div
                v-for="(seg, i) in node.data.segments"
                :key="i"
                class="text-xs bg-gray-800/60 rounded px-2.5 py-1.5"
              >
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-gray-500">[{{ (i as number) + 1 }}]</span>
                  <span class="text-gray-600">{{ seg.collection }}</span>
                  <span class="ml-auto text-gray-600">{{ seg.score }}</span>
                </div>
                <div class="text-gray-400 leading-relaxed line-clamp-2">{{ seg.text }}</div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div v-if="error" class="mt-3 p-3 rounded-lg bg-red-950/50 border border-red-800 text-red-400 text-xs">
      ✕ {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()

const MIN_DISPLAY_MS = 1200

interface StepEntry {
  node_name: string
  status: 'started' | 'completed' | 'error' | 'failed'
  summary: string
  timestamp: string
  data?: Record<string, any> | null
}

interface MergedNode {
  node_name: string
  displayStatus: 'started' | 'completed' | 'error'
  summary: string
  timestamp: string
  data?: Record<string, any> | null
  startedAt?: number
}

const props = defineProps<{
  steps: StepEntry[]
  isRunning: boolean
  error?: string | null
}>()

const nodeMap = ref<Map<string, MergedNode>>(new Map())
const expanded = ref<Set<string>>(new Set())

// ── Async sequential queue ─────────────────────────────────────────────────
const _queue: StepEntry[] = []
let _isProcessing = false
let _processedCount = 0
let _stopped = false

onUnmounted(() => { _stopped = true; _queue.length = 0 })

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

watch(
  () => props.steps,
  (newSteps) => {
    // Steps array was reset (e.g. user started a new report) — clear internal state
    if (newSteps.length < _processedCount) {
      nodeMap.value.clear()
      expanded.value.clear()
      _processedCount = 0
      _queue.length = 0
      _isProcessing = false
    }
    const fresh = newSteps.slice(_processedCount)
    _processedCount = newSteps.length
    _queue.push(...fresh)
    if (!_isProcessing) { _isProcessing = true; drainQueue() }
  },
  { deep: true },
)

async function drainQueue() {
  while (_queue.length > 0 && !_stopped) {
    await applyStep(_queue.shift()!)
  }
  _isProcessing = false
}

async function applyStep(step: StepEntry) {
  if (_stopped) return
  const key = step.node_name
  const norm = (step.status === 'failed' ? 'error' : step.status) as 'started' | 'completed' | 'error'
  const existing = nodeMap.value.get(key)

  if (norm === 'started') {
    // Show immediately; drainQueue will move on to the next item
    // (the paired completed event) which will then await the min delay.
    nodeMap.value.set(key, {
      node_name: step.node_name,
      displayStatus: 'started',
      summary: step.summary,
      timestamp: step.timestamp,
      data: step.data ?? null,
      startedAt: Date.now(),
    })
  } else {
    // completed / error: enforce minimum display time from when started was shown
    const elapsed = existing?.startedAt ? Date.now() - existing.startedAt : MIN_DISPLAY_MS
    await sleep(Math.max(0, MIN_DISPLAY_MS - elapsed))
    if (_stopped) return
    const node = nodeMap.value.get(key)
    const target = node ?? (() => {
      const n: MergedNode = { node_name: key, displayStatus: norm, summary: step.summary, timestamp: step.timestamp }
      nodeMap.value.set(key, n); return n
    })()
    target.displayStatus = norm
    target.summary = step.summary
    target.timestamp = step.timestamp
    if (step.data) target.data = step.data
  }
}

const mergedNodes = computed(() => Array.from(nodeMap.value.values()))

function toggleExpand(nodeName: string) {
  if (expanded.value.has(nodeName)) {
    expanded.value.delete(nodeName)
  } else {
    expanded.value.add(nodeName)
  }
}

function translateNode(nodeName: string): string {
  const key = `agent.nodes.${nodeName}`
  const result = t(key)
  return result === key ? nodeName : result
}

function nodeClass(status: string) {
  return {
    started: 'bg-yellow-950/30 border-yellow-800/50',
    completed: 'bg-green-950/30 border-green-800/50',
    error: 'bg-red-950/30 border-red-800/50',
  }[status] ?? 'bg-gray-800/30 border-gray-700/50'
}

function nodeNameClass(status: string) {
  return {
    started: 'text-yellow-400',
    completed: 'text-green-400',
    error: 'text-red-400',
  }[status] ?? 'text-gray-400'
}

function formatTime(iso: string) {
  try {
    const localeStr = locale.value === 'zh' ? 'zh-CN' : 'en-US'
    const s = new Date(iso).toLocaleTimeString(localeStr, {
      timeZone: 'Asia/Shanghai',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    })
    return `${s} (UTC+8)`
  } catch { return '' }
}
</script>
