import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/matches' },
    {
      path: '/matches',
      component: () => import('@/views/MatchListView.vue'),
    },
    {
      path: '/matches/:id',
      component: () => import('@/views/MatchDetailView.vue'),
    },
    {
      path: '/pre-match',
      component: () => import('@/views/PreMatchView.vue'),
    },
    {
      path: '/chat',
      component: () => import('@/views/ChatView.vue'),
    },
  ],
})

export default router
