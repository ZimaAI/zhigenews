import { createRouter, createWebHistory } from 'vue-router';
import Overview from './pages/Overview.vue';
import Sources from './pages/Sources.vue';
import Models from './pages/Models.vue';
import AgentConfigs from './pages/AgentConfigs.vue';
import Runs from './pages/Runs.vue';
import Evaluations from './pages/Evaluations.vue';
import Users from './pages/Users.vue';
import Deliveries from './pages/Deliveries.vue';
import Login from './pages/Login.vue';
import { anonymousAdminApi } from '@shared/anonymous';
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/', redirect: '/overview' },
  { path: '/overview', component: Overview },
  { path: '/sources/:id?', component: Sources },
  { path: '/models', component: Models },
  { path: '/agent-configs', component: AgentConfigs },
  { path: '/runs/:id?', component: Runs },
  { path: '/evaluations/:id?', component: Evaluations },
  { path: '/users', component: Users },
  { path: '/deliveries', component: Deliveries },
  { path: '/login', component: Login },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
], scrollBehavior(to, from, saved) { return saved || (to.path === from.path ? {} : { top: 0 }); } });

router.beforeEach(async to => { if (to.path === '/login') return; try { await anonymousAdminApi.session(); } catch { return '/login'; } });
export default router;
