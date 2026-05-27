<template>
  <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
    <h3 class="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
      <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse" v-if="isRunning"></span>
      <span class="w-2 h-2 rounded-full bg-gray-500" v-else></span>
      {{ t('agent.title') }}
    </h3>
    <div v-if="steps.length === 0" class="text-sm text-gray-600 italic py-2">
      {{ t('agent.waiting') }}
    </div>
    <div class="space-y-2">
      <div
        v-for="(step, i) in steps"
        :key="i"
        class="flex items-start gap-3 p-2.5 rounded-lg border text-sm transition-all"
        :class="stepClass(step.status)"
      >
        <span class="mt-0.5 text-base shrink-0">{{ stepIcon(step.status) }}</span>
        <div class="flex-1 min-w-0">
          <div class="font-mono text-xs font-medium" :class="stepNameClass(step.status)">
            {{ step.node_name }}
          </div>
          <div class="text-gray-400 text-xs mt-0.5 truncate">{{ step.summary }}</div>
        </div>
        <div class="text-xs text-gray-600 shrink-0">
          {{ formatTime(step.timestamp) }}
        </div>
      </div>
    </div>
    <div v-if="error" class="mt-3 p-3 rounded-lg bg-red-950/50 border border-red-800 text-red-400 text-xs">
      ❌ {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

interface StepEntry {
  node_name: string
  status: 'started' | 'completed' | 'failed'
  summary: string
  timestamp: string
}

defineProps<{
  steps: StepEntry[]
  isRunning: boolean
  error?: string | null
}>()

function stepIcon(status: string) {
  return { started: '⏳', completed: '✅', failed: '❌' }[status] ?? '⬜'
}

function stepClass(status: string) {
  return {
    started: 'bg-yellow-950/30 border-yellow-800/50',
    completed: 'bg-green-950/30 border-green-800/50',
    failed: 'bg-red-950/30 border-red-800/50',
  }[status] ?? 'bg-gray-800/30 border-gray-700/50'
}

function stepNameClass(status: string) {
  return {
    started: 'text-yellow-400',
    completed: 'text-green-400',
    failed: 'text-red-400',
  }[status] ?? 'text-gray-400'
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}
</script>
