import { createRouter, createWebHistory } from 'vue-router';
import Today from './pages/Today.vue';
import Brief from './pages/Brief.vue';
import History from './pages/History.vue';
import Preferences from './pages/Preferences.vue';
import Delivery from './pages/Delivery.vue';
import Onboarding from './pages/Onboarding.vue';
import Auth from './pages/Auth.vue';
import Settings from './pages/Settings.vue';
import { state } from '@shared/mock';
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/today', component: Today, meta: { title: '今日简报' } },
    { path: '/briefs', component: History, meta: { title: '历史简报' } },
    { path: '/briefs/:id', component: Brief, meta: { title: '阅读简报' } },
    { path: '/preferences', redirect: '/settings/preferences' },
    { path: '/delivery', redirect: '/settings/schedule' },
    { path: '/onboarding', component: Onboarding, meta: { title: '订阅偏好' } },
    { path: '/runs/:id', redirect: '/today' },
    { path: '/settings', component: Settings, meta: { title: '个人设置' }, children: [
      { path: '', redirect: '/settings/preferences' },
      { path: 'preferences', component: Preferences, meta: { title: '订阅偏好' } },
      { path: 'schedule', component: Delivery, meta: { title: '推送时间' } },
    ] },
    { path: '/login', component: Auth, meta: { title: '欢迎', standalone: true } },
    { path: '/register', redirect: '/login' },
    { path: '/:pathMatch(.*)*', redirect: '/today' },
  ],
  scrollBehavior(to, from, saved) {
    if (to.hash) return { el: to.hash, top: 24 };
    if (to.path === from.path) return;
    return saved ?? { top: 0 };
  },
});
router.beforeEach((to) => {
  if (to.meta.standalone) return;
  if (!state.authenticated) return { path: '/login', query: { next: to.fullPath } };
  if (!state.onboardingCompleted && to.path !== '/onboarding') return '/onboarding';
  if (state.onboardingCompleted && to.path === '/onboarding') return '/today';
});
router.afterEach((to) => { document.title = `${to.meta.title || '简报'} · 知更`; });
export default router;
