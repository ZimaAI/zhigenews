<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import BrandLogo from '@ui/BrandLogo.vue';
import IcpLink from './IcpLink.vue';
import { History, Newspaper } from 'lucide-vue-next';
import { sessionState } from '../state';
const route = useRoute();
const name = computed(() => sessionState.session?.name || '匿名读者');
const navigation = [{ path: '/today', label: '今日简报', icon: Newspaper }, { path: '/briefs', label: '历史简报', icon: History }];
const active = (path: string) => route.path === path || route.path.startsWith(`${path}/`);
</script>
<template>
  <a class="skip-link" href="#reader-main">跳转到主要内容</a>
  <div class="reader-shell">
    <header class="reader-masthead">
      <RouterLink to="/today" class="reader-brand" aria-label="知更 · 今日简报"><BrandLogo decorative /><span>知更</span></RouterLink>
      <div class="reader-utilities"><RouterLink v-if="sessionState.session?.onboardingCompleted" to="/settings" class="reader-account" :class="{ selected: active('/settings') }" aria-label="个人设置" :title="name + ' · 个人设置'" :aria-current="active('/settings') ? 'page' : undefined">{{ name.slice(0, 1) }}</RouterLink></div>
    </header>
    <div class="reader-canvas">
      <nav v-if="sessionState.session?.onboardingCompleted" class="reader-nav" aria-label="主要导航"><RouterLink v-for="item in navigation" :key="item.path" :to="item.path" :class="{ selected: active(item.path) }" :aria-current="active(item.path) ? 'page' : undefined"><component :is="item.icon" :size="18" :stroke-width="1.8" aria-hidden="true" />{{ item.label }}</RouterLink></nav>
      <main id="reader-main" class="reader-main" tabindex="-1"><slot /></main>
      <footer class="reader-footer"><IcpLink /></footer>
    </div>
  </div>
</template>
<style scoped>
.reader-shell { width: min(var(--width-page), calc(100% - 64px)); margin: 0 auto 32px; }
.reader-masthead { min-height: 80px; display: flex; align-items: center; gap: 24px; }
.reader-brand { min-height: 44px; display: inline-flex; align-items: center; gap: 10px; text-decoration: none; color: var(--color-primary); }
.reader-brand > span { color: var(--color-text); font-size: 22px; font-weight: 650; line-height: 1.2; }
.reader-utilities { margin-left: auto; display: flex; align-items: center; gap: 24px; }
.reader-account { width: 40px; height: 40px; border: 1px solid var(--color-primary-border); border-radius: 50%; display: grid; place-items: center; background: var(--color-primary-soft); color: var(--color-primary); text-decoration: none; font-size: 14px; font-weight: 600; }
.reader-account:hover, .reader-account.selected { border-color: var(--color-primary); }
.reader-canvas { display: flex; flex-direction: column; background: var(--color-surface); border-radius: 8px; box-shadow: var(--shadow-canvas); min-height: calc(100vh - 112px); }
.reader-footer { margin-top: auto; padding: 8px 16px 16px; text-align: center; }
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
}
</style>
