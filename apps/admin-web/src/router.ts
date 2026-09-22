import { createRouter, createWebHistory } from 'vue-router';
import { ApiError } from '@zhigenews/api-client';
import { loadSession, session, sessionError } from './session';
import { errorText } from './lib';
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', redirect: '/overview' },
  { path: '/overview', component: () => import('./pages/Overview.vue') },
  { path: '/sources/:id?', component: () => import('./pages/Sources.vue') },
  { path: '/runs/:id?', component: () => import('./pages/Runs.vue') },
  { path: '/users', component: () => import('./pages/Users.vue') },
  { path: '/deliveries', component: () => import('./pages/Deliveries.vue') },
  { path: '/login', component: () => import('./pages/Login.vue') },
  { path: '/:pathMatch(.*)*', component: () => import('./pages/NotFound.vue') },
], scrollBehavior(to, from, saved) { return saved || (to.path === from.path ? {} : { top: 0 }); } });
router.beforeEach(async to => {
  sessionError.value = '';
  if (to.path === '/login') return;
  try { await loadSession(); }
  catch (error) {
    session.value = null;
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return { path: '/login', query: { redirect: to.fullPath } };
    sessionError.value = errorText(error);
  }
});
window.addEventListener('admin-session-expired', () => { session.value = null; if (router.currentRoute.value.path !== '/login') void router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } }); });
export default router;
