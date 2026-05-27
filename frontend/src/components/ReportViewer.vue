<template>
  <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
    <div class="px-5 py-3 border-b border-gray-800 flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-300">{{ t('report.title') }}</h3>
      <button
        @click="copyToClipboard"
        class="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1 rounded hover:bg-gray-800"
      >
        {{ copied ? t('report.copied') : t('report.copy') }}
      </button>
    </div>
    <div
      class="prose-report px-6 py-5 max-h-[70vh] overflow-y-auto"
      v-html="renderedMarkdown"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMarkdown } from '@/composables/useMarkdown'
const { t } = useI18n()

const props = defineProps<{ markdown: string }>()

const { render } = useMarkdown()
const renderedMarkdown = computed(() => render(props.markdown))

const copied = ref(false)
async function copyToClipboard() {
  await navigator.clipboard.writeText(props.markdown)
  copied.value = true
  setTimeout(() => (copied.value = false), 2000)
}
</script>
