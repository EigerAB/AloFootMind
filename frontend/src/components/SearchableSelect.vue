<template>
  <div ref="containerRef" class="relative">
    <button
      type="button"
      @click="toggle"
      :disabled="disabled"
      class="w-full bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-2 text-left focus:ring-1 focus:ring-green-500 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-between"
    >
      <span :class="modelValue ? 'text-gray-300' : 'text-gray-500'">
        {{ modelValue ? modelValue[displayKey] : placeholder }}
      </span>
      <svg class="w-4 h-4 text-gray-500 transition-transform" :class="open ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    </button>

    <div
      v-if="open"
      class="absolute z-20 w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg overflow-hidden"
    >
      <div class="p-2 border-b border-gray-700">
        <input
          v-model="query"
          type="text"
          :placeholder="searchPlaceholder"
          class="w-full bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-md px-2 py-1.5 focus:ring-1 focus:ring-green-500 focus:outline-none"
        />
      </div>
      <div class="max-h-48 overflow-y-auto">
        <button
          v-for="item in filtered"
          :key="item[trackKey]"
          @click="select(item)"
          class="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 transition-colors"
          :class="modelValue && modelValue[trackKey] === item[trackKey] ? 'bg-green-900/30 text-green-400' : ''"
        >
          {{ item[displayKey] }}
        </button>
        <div v-if="!filtered.length" class="px-3 py-2 text-sm text-gray-500">{{ noResultsText }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface Props {
  modelValue: Record<string, any> | null
  options: Record<string, any>[]
  disabled?: boolean
  placeholder?: string
  searchPlaceholder?: string
  noResultsText?: string
  trackKey?: string
  displayKey?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  placeholder: 'Select...',
  searchPlaceholder: 'Search...',
  noResultsText: 'No results',
  trackKey: 'id',
  displayKey: 'name',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any> | null): void
  (e: 'select', value: Record<string, any>): void
}>()

const open = ref(false)
const query = ref('')
const containerRef = ref<HTMLElement | null>(null)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter((t) => String(t[props.displayKey]).toLowerCase().includes(q))
})

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    query.value = ''
    setTimeout(() => {
      const input = containerRef.value?.querySelector('input')
      input?.focus()
    }, 0)
  }
}

function select(item: Record<string, any>) {
  emit('update:modelValue', item)
  emit('select', item)
  open.value = false
  query.value = ''
}

function onClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>
