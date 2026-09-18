import { createRouter, createWebHistory } from 'vue-router';
import Today from './pages/Today.vue';
import Brief from './pages/Brief.vue';
import History from './pages/History.vue';
import Preferences from './pages/Preferences.vue';
import Delivery from './pages/Delivery.vue';
import Onboarding from './pages/Onboarding.vue';
import Auth from './pages/Auth.vue';
import Run from './pages/Run.vue';
import Settings from './pages/Settings.vue';
import { state } from '@shared/mock';
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/today', component: Today, meta: { title: '今日简报' } },
    { path: '/briefs', component: History, meta: { title: '历史简报' } },
    { path: '/briefs/:id', component: Brief, meta: { title: '阅读简报' } },
    { path: '/preferences', component: Preferences, meta: { title: '兴趣订阅' } },
    { path: '/delivery', component: Delivery, meta: { title: '推送设置' } },
    { path: '/onboarding', component: Onboarding, meta: { title: '首次配置' } },
    { path: '/runs/:id', component: Run, meta: { title: '整理过程' } },
    { path: '/settings', component: Settings, meta: { title: '设置' } },
    { path: '/login', component: Auth, meta: { title: '登录', standalone: true } },
    { path: '/register', component: Auth, meta: { title: '创建账户', standalone: true } },
    { path: '/:pathMatch(.*)*', redirect: '/today' },
  ],
  scrollBehavior(to, from, saved) { if (to.path === from.path) return; return saved ?? { top: 0 }; },
});
router.beforeEach((to) => { if (!to.meta.standalone && !state.authenticated) return '/login'; });
router.afterEach((to) => { document.title = `${to.meta.title || '简报'} · 知更`; });
export default router;
