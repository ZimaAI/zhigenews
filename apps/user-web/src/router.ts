import { createRouter, createWebHistory } from 'vue-router';
import Today from './pages/Today.vue';
import Brief from './pages/Brief.vue';
import History from './pages/History.vue';
import Preferences from './pages/Preferences.vue';
import Delivery from './pages/Delivery.vue';
import Onboarding from './pages/Onboarding.vue';
import Auth from './pages/Auth.vue';
import Settings from './pages/Settings.vue';
import { restoreSession } from './state';
const router = createRouter({ history: createWebHistory(), routes: [
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
], scrollBehavior(to, from, saved) { if (to.path === from.path) return; return saved ?? { top: 0 }; } });
router.beforeEach(async to => {
  if (to.meta.standalone) return;
  const session = await restoreSession();
  if (!session) return { path: '/login', query: { next: to.fullPath } };
  if (!session.onboardingCompleted && to.path !== '/onboarding') return '/onboarding';
  if (session.onboardingCompleted && to.path === '/onboarding') return '/today';
});
router.afterEach((to, _from, failure) => { if (!failure) document.title = `${to.meta.title || '简报'} · 知更`; });
export default router;
