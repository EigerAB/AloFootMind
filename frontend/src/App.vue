<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'

const route = useRoute()
const noLayout = computed(() => !!route.meta.noLayout)
</script>

<template>
  <template v-if="noLayout">
    <RouterView v-slot="{ Component, route: r }">
      <component :is="Component" :key="r.fullPath" />
    </RouterView>
  </template>
  <AppLayout v-else>
    <RouterView v-slot="{ Component, route: r }">
      <KeepAlive>
        <component :is="Component" v-if="r.meta.keepAlive" :key="r.path" />
      </KeepAlive>
      <component :is="Component" v-if="!r.meta.keepAlive" :key="r.fullPath" />
    </RouterView>
  </AppLayout>
</template>
