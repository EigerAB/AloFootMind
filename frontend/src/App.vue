<script setup lang="ts">
import AppLayout from '@/components/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <RouterView v-slot="{ Component, route }">
      <KeepAlive>
        <component :is="Component" v-if="route.meta.keepAlive" :key="route.path" />
      </KeepAlive>
      <component :is="Component" v-if="!route.meta.keepAlive" :key="route.fullPath" />
    </RouterView>
  </AppLayout>
</template>
