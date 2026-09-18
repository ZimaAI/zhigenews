<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { Activity, ArrowUpRight, BookOpen, CalendarDays, ChevronDown, FlaskConical, History, LayoutDashboard, LogOut, Menu, Newspaper, Radio, RotateCcw, Send, Settings2, SlidersHorizontal, Users, Waypoints } from 'lucide-vue-next';
import { api, resetDemo, resetRevision, setScenario, state, toast } from './mock';
import type { Scenario } from './types';
import Modal from './Modal.vue';
import EmptyState from './EmptyState.vue';
const props = defineProps<{ app: 'user' | 'admin' }>();
const route = useRoute(); const navOpen = ref(false);
const userNav = [{ path: '/today', label: '今日简报', icon: Newspaper }, { path: '/briefs', label: '历史简报', icon: History }, { path: '/preferences', label: '兴趣订阅', icon: SlidersHorizontal }, { path: '/delivery', label: '推送设置', icon: Send }];
const adminNav = [{ path: '/overview', label: '运行概览', icon: LayoutDashboard }, { path: '/sources', label: '新闻来源', icon: Radio }, { path: '/models', label: '模型与端点', icon: Waypoints }, { path: '/agent-configs', label: 'Agent 配置', icon: Settings2 }, { path: '/runs', label: '运行记录', icon: Activity }, { path: '/evaluations', label: '评估实验', icon: FlaskConical }, { path: '/users', label: '用户管理', icon: Users }, { path: '/deliveries', label: '投递记录', icon: Send }];
const nav = computed(() => props.app === 'user' ? userNav : adminNav);
const active = (path: string) => route.path === path || route.path.startsWith(`${path}/`);
const title = computed(() => nav.value.find(x => active(x.path))?.label || (route.meta.title as string) || '知更');
const switchUrl = computed(() => props.app === 'user' ? 'http://127.0.0.1:5174' : 'http://127.0.0.1:5173');
const mobileNav = computed(() => props.app === 'user' ? [userNav[0]!, userNav[1]!, { path: '/settings', label: '设置', icon: Settings2 }] : [adminNav[0]!, adminNav[4]!, adminNav[5]!]);
const scenarios: { value: Scenario; label: string }[] = [{ value: 'normal', label: '正常内容' }, { value: 'loading', label: '加载过程' }, { value: 'empty', label: '空内容 / 首次使用' }, { value: 'error', label: '请求失败' }, { value: 'partial', label: '部分完成' }, { value: 'unauthorized', label: '无权限' }];
async function retry() { state.scenario = 'normal'; await api.load(); }
</script>
<template>
  <a class="skip-link" href="#main-content">跳转到主要内容</a>
  <div class="app-shell" :class="`app-shell--${app}`">
    <aside class="sidebar"><RouterLink class="brand" :to="app === 'user' ? '/today' : '/overview'"><span class="brand-mark"><BookOpen :size="23" :stroke-width="1.7" /></span><span class="brand-name">知更<span>ZHIGE BRIEF</span></span></RouterLink><div class="sidebar-section-label">{{ app === 'user' ? '你的每日阅读' : '工作空间' }}</div><nav class="desktop-nav" aria-label="主要导航"><RouterLink v-for="item in nav" :key="item.path" :to="item.path" :aria-current="active(item.path) ? 'page' : undefined" :class="{ selected: active(item.path) }" :title="item.label"><component :is="item.icon" :size="20" :stroke-width="1.7" /><span>{{ item.label }}</span><span v-if="item.path === '/today' && state.briefs[0]" class="nav-count">{{ state.briefs[0].items.length }}</span></RouterLink></nav>
      <div v-if="app === 'user'" class="sidebar-note"><CalendarDays :size="18"/><span>每天一点，保持好奇。</span><p>下一期 · {{ state.delivery.dailyEnabled ? state.delivery.time : '已暂停' }}<br/>{{ state.delivery.timezone }}</p></div>
      <div v-else class="sidebar-note"><span class="small-caps">PROTOTYPE / R1</span><p>独立管理端<br/>所有运行与指标均为示例</p></div>
      <div class="sidebar-account"><span class="avatar">{{ app === 'user' ? '林' : '管' }}</span><div><strong>{{ app === 'user' ? '林序' : '管理员' }}</strong><p>演示账户</p></div><RouterLink to="/login" class="icon-button" aria-label="切换演示账户" title="切换演示账户"><LogOut :size="17" /></RouterLink></div>
    </aside>
    <div class="app-body"><header class="topbar"><div class="row"><button class="button button--ghost icon-button menu-toggle" aria-label="展开导航" @click="navOpen = true"><Menu :size="20" /></button><span class="topbar-product">{{ app === 'user' ? '个人阅读空间' : '知更控制台' }}</span><span class="breadcrumb-divider">/</span><span class="topbar-title">{{ title }}</span></div><div class="topbar-actions"><a :href="switchUrl" target="_blank" rel="noopener" class="app-switch">{{ app === 'user' ? '管理端' : '阅读端' }}<ArrowUpRight :size="14" /></a><details class="prototype-menu"><summary><FlaskConical :size="15" /><span>交互原型</span><ChevronDown :size="14" /></summary><div class="prototype-panel"><strong>示例数据 · 不调用真实服务</strong><p class="meta">固定时钟：2026-09-18 08:12。切换场景会重置当前示例。</p><label class="field">演示场景<select class="field-control" :value="state.scenario" @change="setScenario(($event.target as HTMLSelectElement).value as Scenario)"><option v-for="scene in scenarios" :key="scene.value" :value="scene.value">{{ scene.label }}</option></select></label><button class="button" @click="resetDemo"><RotateCcw :size="15" />重置全部示例</button></div></details></div></header>
      <main id="main-content" class="main-content" tabindex="-1"><div class="demo-caption"><span class="demo-dot"></span>交互原型 · 新闻、运行与推送结果均为示例</div><div v-if="state.scenario === 'error'" class="alert alert--danger"><div><strong>模拟请求失败</strong><p>已显示的内容保留。保存操作将模拟失败，输入不会丢失。</p></div><button class="button" @click="retry">重试加载</button></div><EmptyState v-if="state.scenario === 'unauthorized'" error title="没有访问权限" description="这是权限拒绝的交互示例。真实角色校验将在后端实现。"><button class="button" @click="setScenario('normal')">返回正常场景</button></EmptyState><section v-else-if="!state.loaded" class="loading-state" aria-live="polite" aria-busy="true"><p>正在加载示例内容…</p><div class="skeleton skeleton--heading"></div><div v-for="n in 3" :key="n" class="skeleton"></div></section><div v-show="state.loaded && state.scenario !== 'unauthorized'" :key="resetRevision"><slot /></div></main>
      <footer class="app-footer"><span>知更 · 留一点时间给真正重要的事</span><span>原型 r1 · {{ app === 'user' ? '个人阅读' : '管理工作空间' }}</span></footer>
    </div>
    <nav class="mobile-nav" aria-label="移动导航"><RouterLink v-for="item in mobileNav" :key="item.path" :to="item.path" :class="{ selected: active(item.path) }"><component :is="item.icon" :size="20" /><span>{{ item.label }}</span></RouterLink><button @click="navOpen = true"><Menu :size="20" /><span>更多</span></button></nav>
  </div>
  <Modal :open="navOpen" title="导航" @close="navOpen = false"><nav class="mobile-menu"><RouterLink v-for="item in nav" :key="item.path" :to="item.path" @click="navOpen = false"><component :is="item.icon" :size="20" />{{ item.label }}</RouterLink><RouterLink to="/login" @click="navOpen = false">演示账户</RouterLink></nav></Modal>
  <div v-if="toast" class="toast" role="status">{{ toast }}</div>
</template>
