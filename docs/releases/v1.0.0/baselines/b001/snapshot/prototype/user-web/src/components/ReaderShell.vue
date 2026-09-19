<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowUpRight, BookOpen, ChevronDown, FlaskConical, History, Newspaper, RotateCcw } from 'lucide-vue-next';
import { api, resetDemo, resetRevision, setScenario, state, toast } from '@shared/mock';
import type { Scenario } from '@shared/types';
import EmptyState from '@shared/EmptyState.vue';

const route = useRoute();
const name = computed(() => state.session?.name || state.users[0]?.name || '匿名读者');
const navigation = [
  { path: '/today', label: '今日简报', icon: Newspaper },
  { path: '/briefs', label: '历史简报', icon: History },
];
const active = (path: string) => route.path === path || route.path.startsWith(`${path}/`);
const scenarios: { value: Scenario; label: string }[] = [
  { value: 'normal', label: '正常内容' }, { value: 'loading', label: '加载过程' },
  { value: 'empty', label: '空内容' }, { value: 'error', label: '请求失败' },
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
        <span>知更</span>
      </RouterLink>
      <div class="reader-utilities">
        <details class="prototype-menu">
          <summary><FlaskConical :size="14" aria-hidden="true" /><span>演示</span><ChevronDown :size="13" aria-hidden="true" /></summary>
          <div class="prototype-panel">
            <strong>示例数据 · 不调用真实服务</strong>
            <p class="meta">固定时钟：2026-09-18 08:12。切换场景会重置当前示例。</p>
            <label class="field" for="reader-scenario">演示场景</label>
            <select id="reader-scenario" class="field-control" :value="state.scenario" @change="setScenario(($event.target as HTMLSelectElement).value as Scenario)">
              <option v-for="scene in scenarios" :key="scene.value" :value="scene.value">{{ scene.label }}</option>
            </select>
            <button class="button" @click="resetDemo"><RotateCcw :size="15" aria-hidden="true" />重置全部示例</button>
            <a href="http://127.0.0.1:5174/overview" target="_blank" rel="noopener" class="reader-admin-link">管理端<ArrowUpRight :size="13" aria-hidden="true" /></a>
          </div>
        </details>
        <RouterLink v-if="state.onboardingCompleted" to="/settings" class="reader-account" :class="{ selected: active('/settings') }" aria-label="个人设置" :title="name + ' · 个人设置'" :aria-current="active('/settings') ? 'page' : undefined">{{ name.slice(0, 1) }}</RouterLink>
      </div>
    </header>

    <div class="reader-canvas">
      <nav v-if="state.onboardingCompleted" class="reader-nav" aria-label="主要导航">
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path" :class="{ selected: active(item.path) }" :aria-current="active(item.path) ? 'page' : undefined">
          <component :is="item.icon" :size="18" :stroke-width="1.8" aria-hidden="true" />{{ item.label }}
        </RouterLink>
      </nav>
      <main id="reader-main" class="reader-main" tabindex="-1">
        <div v-if="state.scenario === 'error'" class="alert alert--danger"><strong>加载失败</strong><button class="button" @click="retry">重试加载</button></div>
        <EmptyState v-if="state.scenario === 'unauthorized'" error title="没有访问权限" description=""><button class="button" @click="setScenario('normal')">返回</button></EmptyState>
        <section v-else-if="!state.loaded" aria-live="polite" aria-busy="true"><p class="meta">加载中…</p><div class="skeleton skeleton--heading"></div><div v-for="n in 3" :key="n" class="skeleton"></div></section>
        <div v-show="state.loaded && state.scenario !== 'unauthorized'" :key="resetRevision"><slot /></div>
      </main>
    </div>
  </div>
  <div v-if="toast" class="toast" role="status">{{ toast }}</div>
</template>

<style scoped>
.reader-shell { width: min(var(--width-page), calc(100% - 64px)); margin: 0 auto 32px; }
.reader-masthead { min-height: 80px; display: flex; align-items: center; gap: 24px; }
.reader-brand { display: inline-flex; align-items: center; gap: 10px; text-decoration: none; color: var(--color-primary); }
.reader-brand > span { color: var(--color-text); font-size: 22px; font-weight: 650; line-height: 1.2; }
.reader-utilities { margin-left: auto; display: flex; align-items: center; gap: 24px; }
.reader-admin-link { display: inline-flex; align-items: center; gap: 4px; text-decoration: none; color: var(--color-text-muted); font-size: 12px; }
.reader-account { width: 40px; height: 40px; border: 1px solid var(--color-primary-border); border-radius: 50%; display: grid; place-items: center; background: var(--color-primary-soft); color: var(--color-primary); text-decoration: none; font-size: 14px; font-weight: 600; }
.reader-account:hover, .reader-account.selected { border-color: var(--color-primary); }
.prototype-menu { z-index: 30; }
.prototype-menu > summary { background: transparent; border-color: transparent; min-height: 40px; font-size: 12px; }
.reader-canvas { background: var(--color-surface); border-radius: 8px; box-shadow: var(--shadow-canvas); min-height: calc(100vh - 112px); }
.reader-nav { display: flex; gap: 36px; margin-inline: 48px; border-bottom: 1px solid var(--color-border); padding-top: 12px; min-width: 0; overflow-x: auto; }
.reader-nav a { display: inline-flex; align-items: center; flex-shrink: 0; gap: 8px; min-height: 56px; padding: 8px 0 5px; border-bottom: 2px solid transparent; color: var(--color-text-muted); text-decoration: none; font-size: 14px; }
.reader-nav a:hover { color: var(--color-primary); }
.reader-nav a.selected { color: var(--color-primary); border-bottom-color: var(--color-accent); font-weight: 600; }
.reader-main { padding: 40px 48px 48px; min-width: 0; outline: none; }
.reader-main:focus-visible { outline: 2px solid var(--color-primary); outline-offset: -4px; }
@media (max-width: 1023px) {
  .reader-shell { width: calc(100% - 40px); }
  .reader-nav { margin-inline: 32px; }
  .reader-main { padding: 32px; }
}
@media (max-width: 767px) {
  .reader-shell { width: 100%; }
  .reader-masthead { min-height: 72px; padding: 12px 16px; gap: 12px; }
  .reader-brand > span { font-size: 20px; }
  .reader-utilities { gap: 8px; }
  .reader-account { min-width: 44px; min-height: 44px; }
  .reader-canvas { border-radius: 0; box-shadow: none; }
  .reader-nav { margin-inline: 16px; padding-top: 0; gap: 24px; }
  .reader-nav a { min-height: 56px; font-size: 13px; gap: 6px; }
  .reader-main { padding: 28px 16px 32px; }
  .prototype-panel { top: 68px; }
}
</style>
