<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowUpRight, BookOpen, ChevronDown, FlaskConical, History, Newspaper, RotateCcw, Rss, Send, UserRound } from 'lucide-vue-next';
import { api, resetDemo, resetRevision, setScenario, state, toast } from '@shared/mock';
import type { Scenario } from '@shared/types';
import EmptyState from '@shared/EmptyState.vue';
import Modal from '@shared/Modal.vue';

const route = useRoute();
const accountOpen = ref(false);
const name = computed(() => state.users[0]?.name || '新读者');
const navigation = [
  { path: '/today', label: '今日简报', icon: Newspaper },
  { path: '/briefs', label: '历史简报', icon: History },
  { path: '/preferences', label: '兴趣订阅', icon: Rss },
  { path: '/delivery', label: '推送设置', icon: Send },
];
const active = (path: string) => route.path === path || route.path.startsWith(`${path}/`) || (path === '/preferences' && route.path === '/onboarding');
const scenarios: { value: Scenario; label: string }[] = [
  { value: 'normal', label: '正常内容' }, { value: 'loading', label: '加载过程' },
  { value: 'empty', label: '空内容 / 首次使用' }, { value: 'error', label: '请求失败' },
  { value: 'partial', label: '部分完成' }, { value: 'unauthorized', label: '无权限' },
];
async function retry() { state.scenario = 'normal'; await api.load(); }
</script>

<template>
  <a class="skip-link" href="#reader-main">跳转到主要内容</a>
  <div class="reader-shell">
    <header class="reader-masthead">
      <RouterLink to="/today" class="reader-brand" aria-label="知更 · 今日简报">
        <BookOpen :size="27" :stroke-width="1.8" aria-hidden="true" />
        <span>知更<span class="reader-wordmark">ZHIGE BRIEF</span></span>
      </RouterLink>
      <span class="reader-tagline">每天，读点关心的事。</span>
      <div class="reader-utilities">
        <a href="http://127.0.0.1:5174/overview" target="_blank" rel="noopener" class="reader-admin-link">管理端<ArrowUpRight :size="13" aria-hidden="true" /></a>
        <details class="prototype-menu">
          <summary><FlaskConical :size="14" aria-hidden="true" /><span>交互原型</span><ChevronDown :size="13" aria-hidden="true" /></summary>
          <div class="prototype-panel">
            <strong>示例数据 · 不调用真实服务</strong>
            <p class="meta">固定时钟：2026-09-18 08:12。切换场景会重置当前示例。</p>
            <label class="field" for="reader-scenario">演示场景</label>
            <select id="reader-scenario" class="field-control" :value="state.scenario" @change="setScenario(($event.target as HTMLSelectElement).value as Scenario)">
              <option v-for="scene in scenarios" :key="scene.value" :value="scene.value">{{ scene.label }}</option>
            </select>
            <button class="button" @click="resetDemo"><RotateCcw :size="15" aria-hidden="true" />重置全部示例</button>
          </div>
        </details>
        <button class="reader-account" aria-label="账户与设置" @click="accountOpen = true"><UserRound :size="18" aria-hidden="true" /></button>
      </div>
    </header>

    <div class="reader-canvas">
      <nav class="reader-nav" aria-label="主要导航">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path" :class="{ selected: active(item.path) }" :aria-current="active(item.path) ? 'page' : undefined">
          <component :is="item.icon" :size="18" :stroke-width="1.6" aria-hidden="true" />{{ item.label }}
        </RouterLink>
      </nav>
      <main id="reader-main" class="reader-main" tabindex="-1">
        <div v-if="state.scenario === 'error'" class="alert alert--danger"><div><strong>模拟请求失败</strong><p>保存操作将模拟失败，已显示内容和输入会保留。</p></div><button class="button" @click="retry">重试加载</button></div>
        <EmptyState v-if="state.scenario === 'unauthorized'" error title="没有访问权限" description="这是权限拒绝的交互示例。真实角色校验将在后端实现。"><button class="button" @click="setScenario('normal')">返回正常场景</button></EmptyState>
        <section v-else-if="!state.loaded" aria-live="polite" aria-busy="true"><p class="meta">正在加载示例内容…</p><div class="skeleton skeleton--heading"></div><div v-for="n in 3" :key="n" class="skeleton"></div></section>
        <div v-show="state.loaded && state.scenario !== 'unauthorized'" :key="resetRevision"><slot /></div>
      </main>
    </div>
    <footer class="reader-footer"><span>知更 · 留一点时间给真正重要的事</span><span>交互原型 r2 · 新闻与推送均为示例</span></footer>
  </div>
  <Modal :open="accountOpen" title="你的阅读空间" @close="accountOpen = false">
    <p class="reader-account-name">{{ name }}<span class="meta">演示账户</span></p>
    <nav class="mobile-menu" aria-label="账户导航">
      <RouterLink to="/settings" @click="accountOpen = false">阅读设置</RouterLink>
      <RouterLink to="/onboarding" @click="accountOpen = false">首次订阅引导</RouterLink>
      <RouterLink to="/login" @click="accountOpen = false">切换演示账户</RouterLink>
    </nav>
  </Modal>
  <div v-if="toast" class="toast" role="status">{{ toast }}</div>
</template>

<style scoped>
.reader-shell { width: min(var(--width-page), calc(100% - 64px)); margin: 0 auto; }
.reader-masthead { min-height: 96px; display: flex; align-items: center; gap: 24px; }
.reader-brand { display: inline-flex; align-items: center; gap: 10px; text-decoration: none; color: var(--color-primary); }
.reader-brand > span { color: var(--color-text); font-size: 22px; font-weight: 650; line-height: 1.2; }
.reader-wordmark { display: block; font-size: 8px; letter-spacing: 1.7px; font-weight: 500; margin-top: 5px; color: var(--color-text-muted); }
.reader-tagline { font-size: 12px; color: var(--color-text-muted); padding-left: 24px; border-left: 1px solid var(--color-border); }
.reader-utilities { margin-left: auto; display: flex; align-items: center; gap: 24px; }
.reader-admin-link { display: inline-flex; align-items: center; gap: 4px; text-decoration: none; color: var(--color-text-muted); font-size: 12px; }
.reader-account { width: 36px; height: 36px; border: 1px solid var(--color-border); border-radius: 50%; display: grid; place-items: center; background: var(--color-surface); color: var(--color-text-secondary); }
.reader-account:hover { border-color: var(--color-primary); color: var(--color-primary); }
.reader-account-name { display: flex; align-items: center; gap: 12px; }
.prototype-menu { z-index: 30; }
.prototype-menu > summary { background: transparent; border-color: transparent; min-height: 40px; font-size: 12px; }
.reader-canvas { background: var(--color-surface); border-radius: 8px; box-shadow: var(--shadow-canvas); min-height: calc(100vh - 164px); }
.reader-nav { display: flex; gap: 36px; margin-inline: 48px; border-bottom: 1px solid var(--color-border); padding-top: 12px; min-width: 0; overflow-x: auto; }
.reader-nav a { display: inline-flex; align-items: center; flex-shrink: 0; gap: 10px; min-height: 65px; padding: 8px 0 5px; border-bottom: 2px solid transparent; color: var(--color-text-muted); text-decoration: none; font-size: 14px; }
.reader-nav a:hover { color: var(--color-primary); }
.reader-nav a.selected { color: var(--color-primary); border-bottom-color: var(--color-accent); font-weight: 600; }
.reader-main { padding: 40px 48px 48px; min-width: 0; outline: none; }
.reader-main:focus-visible { outline: 2px solid var(--color-primary); outline-offset: -4px; }
.reader-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; padding: 24px 0; color: var(--color-text-muted); font-size: 11px; }
@media (max-width: 1023px) {
  .reader-shell { width: calc(100% - 40px); }
  .reader-nav { margin-inline: 32px; }
  .reader-main { padding: 32px; }
  .reader-tagline { display: none; }
}
@media (max-width: 767px) {
  .reader-shell { width: 100%; }
  .reader-masthead { min-height: 72px; padding: 12px 16px; gap: 12px; }
  .reader-brand > span { font-size: 20px; }
  .reader-wordmark { font-size: 7px; }
  .reader-utilities { gap: 8px; }
  .reader-account { min-width: 44px; min-height: 44px; }
  .reader-admin-link { display: none; }
  .reader-canvas { border-radius: 0; box-shadow: none; }
  .reader-nav { margin-inline: 16px; padding-top: 0; gap: 24px; }
  .reader-nav a { min-height: 56px; font-size: 13px; gap: 6px; }
  .reader-nav a svg { display: none; }
  .reader-main { padding: 28px 16px 32px; }
  .reader-footer { padding: 20px 16px calc(20px + env(safe-area-inset-bottom)); font-size: 10px; }
  .prototype-panel { top: 68px; }
}
</style>
