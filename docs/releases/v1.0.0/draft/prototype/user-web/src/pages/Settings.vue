<script setup lang="ts">
import { useRouter } from 'vue-router';
import { SlidersHorizontal, Mail, ArrowRight, UserRound, LogOut, Compass } from 'lucide-vue-next';
import { state, api } from '@shared/mock';
const router = useRouter();
function logout() { api.logout(); router.push('/login'); }
</script>
<template>
  <div class="user-form"><header class="page-header"><div><p class="eyebrow">YOUR SPACE</p><h1>设置</h1><p class="muted">管理你的兴趣、推送计划与账户。</p></div></header><div class="settings-account card"><UserRound :size="24" aria-hidden="true" /><div><strong>演示读者</strong><p class="meta">本地原型账户 · 不连接真实服务</p></div></div><nav class="settings-nav card" aria-label="设置页面"><RouterLink to="/preferences"><SlidersHorizontal :size="20" aria-hidden="true" /><div><strong>兴趣订阅</strong><p>{{ state.preferences.topics.join('、') || '尚未设置关注主题' }}</p></div><ArrowRight :size="17" aria-hidden="true" /></RouterLink><RouterLink to="/delivery"><Mail :size="20" aria-hidden="true" /><div><strong>推送设置</strong><p>{{ state.delivery.dailyEnabled ? `每天 ${state.delivery.time} · ${state.delivery.timezone}` : '每日推送已暂停' }}</p></div><ArrowRight :size="17" aria-hidden="true" /></RouterLink><RouterLink to="/onboarding"><Compass :size="20" aria-hidden="true" /><div><strong>首次配置向导</strong><p>重新体验关注方向与推送配置。</p></div><ArrowRight :size="17" aria-hidden="true" /></RouterLink></nav><button class="button logout-button" @click="logout"><LogOut :size="16" aria-hidden="true" />退出演示账户</button></div>
</template>
<style scoped>
.settings-account { display: flex; align-items: center; gap: 16px; }
.settings-account > svg { color: var(--color-primary); }
.settings-account p { margin: 4px 0 0; }
.settings-nav { padding-block: 0; }
.settings-nav a { display: flex; align-items: center; gap: 16px; padding-block: 24px; border-bottom: 1px solid var(--color-border); text-decoration: none; color: var(--color-text); }
.settings-nav a:last-child { border: 0; }
.settings-nav a > svg:first-child { color: var(--color-primary); flex-shrink: 0; }
.settings-nav a > svg:last-child { margin-left: auto; flex-shrink: 0; }
.settings-nav a > div { min-width: 0; }
.settings-nav strong { font-size: 14px; }
.settings-nav p { font-size: 13px; color: var(--color-text-muted); margin: 4px 0 0; overflow-wrap: anywhere; }
.logout-button { margin-top: 24px; }
</style>
