import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/matches' },
    {
      path: '/matches',
      component: () => import('@/views/MatchListView.vue'),
      meta: { keepAlive: true },
    },
    {
      path: '/matches/:id',
      component: () => import('@/views/MatchDetailView.vue'),
    },
    {
      path: '/pre-match',
      component: () => import('@/views/PreMatchView.vue'),
      meta: { keepAlive: true },
    },
    {
      path: '/chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { keepAlive: true },
    },
  ],
})

export default router
