import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'projects',
      component: () => import('@/views/ProjectListView.vue'),
    },
    {
      path: '/verify',
      name: 'email-verify',
      component: () => import('@/views/EmailVerifyView.vue'),
      meta: { public: true },
    },
    {
      path: '/project/:id',
      name: 'project-detail',
      component: () => import('@/views/ProjectDetailView.vue'),
      props: true,
    },
    {
      path: '/project/:id/automation',
      name: 'automation',
      component: () => import('@/views/AutomationView.vue'),
      props: true,
    },
    {
      path: '/keys',
      name: 'key-management',
      component: () => import('@/views/KeyManagementView.vue'),
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/views/NotificationView.vue'),
    },
    {
      path: '/user-center',
      name: 'user-center',
      component: () => import('@/views/UserCenterView.vue'),
    },
  ],
})

export default router
