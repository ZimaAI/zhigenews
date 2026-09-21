<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import BrandLogo from '@ui/BrandLogo.vue';
import { ArrowRight, LoaderCircle, RefreshCw } from 'lucide-vue-next';
import { sessionState, enterSession, restoreSession } from '../state';
import { useRequestState } from '../useRequestState';
const router = useRouter(), route = useRoute();
const busy = ref(false);
const { error, remaining, fail, clear } = useRequestState();
if (sessionState.error) fail(sessionState.error);
async function enter() {
  if (busy.value || remaining.value) return;
  busy.value = true; clear();
  try {
    if (sessionState.error) {
      await restoreSession(true);
      if (sessionState.error) throw sessionState.error;
    }
    if (!sessionState.session) await enterSession();
    const next = typeof route.query.next === 'string' ? route.query.next : '/today';
    await router.replace(next.startsWith('/') && !next.startsWith('//') && !/^\/(login|register)(\?|$)/.test(next) ? next : '/today');
  } catch (exception) { fail(exception); } finally { busy.value = false; }
}
onMounted(() => { if (!error.value) void enter(); });
</script>
<template>
  <main class="auth-page">
    <a class="skip-auth" href="#entry-card">跳转到进入状态</a>
    <div class="auth-brand"><BrandLogo decorative /><span>知更<span class="brand-en">QUIET BRIEF</span></span></div>
    <div class="auth-layout">
      <section class="auth-intro"><p class="eyebrow">LESS NOISE. MORE SIGNAL.</p><h1>每天，读一点<br />真正关心的事。</h1><p>你的兴趣，你的阅读节奏。</p><div class="auth-preview"><span>有来源的 AI 新闻简报</span><p>为你保留值得关注的进展。</p></div></section>
      <section id="entry-card" class="auth-card" :aria-busy="busy">
        <div class="entry-icon"><BrandLogo :size="48" decorative /></div>
        <h2>你的阅读空间</h2><p class="muted">无需注册，即刻开始。</p>
        <template v-if="error"><p class="alert alert--danger" role="alert">{{ error }}</p><button class="button button--primary auth-submit" :disabled="busy || remaining > 0" @click="enter"><RefreshCw :size="16" aria-hidden="true" />{{ busy ? '正在进入…' : remaining > 0 ? remaining + ' 秒后可重试' : '重新进入' }}</button></template>
        <div v-else class="entry-status" role="status"><LoaderCircle :size="18" class="entry-loading" aria-hidden="true" /><span>正在为你打开…</span><ArrowRight :size="16" aria-hidden="true" /></div>
        <p class="auth-note">匿名访问 · 通过当前浏览器 Cookie 恢复偏好</p>
      </section>
    </div>
    <footer class="auth-footer">知更 · 每天读一点真正关心的事</footer>
  </main>
</template>
<style scoped>
.auth-page { max-width: 1200px; margin: auto; padding: 40px; min-height: 100vh; }
.skip-auth { position: absolute; left: -10000px; }
.skip-auth:focus { left: 20px; top: 8px; }
.auth-brand { display: inline-flex; align-items: center; gap: 12px; color: var(--color-primary); font-size: 24px; font-weight: 600; }
.auth-brand > span { display: flex; align-items: center; gap: 16px; }
.brand-en { color: var(--color-text-muted); font-size: 11px; font-weight: 500; letter-spacing: 2px; }
.auth-layout { display: grid; grid-template-columns: minmax(0,1fr) 420px; align-items: center; gap: 80px; margin-block: 88px 80px; }
.auth-intro h1 { font-size: 40px; line-height: 56px; margin: 20px 0; font-weight: 600; }
.auth-intro > p:not(.eyebrow) { font-size: 16px; line-height: 28px; max-width: 380px; color: var(--color-text-secondary); }
.auth-preview { margin-top: 40px; padding-left: 20px; border-left: 2px solid var(--color-primary-border); }
.auth-preview p { margin: 8px 0; font-size: 14px; color: var(--color-text-muted); }
.auth-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-card); padding: 32px; }
.entry-icon { display: grid; place-items: center; width: 48px; height: 48px; margin-bottom: 24px; }
.auth-card h2 { margin: 0 0 8px; font-size: 24px; }
.auth-card > .muted { margin: 0 0 32px; font-size: 14px; }
.entry-status { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 48px; background: var(--color-primary-soft); border-radius: var(--radius-control); color: var(--color-primary); font-size: 14px; }
.entry-loading { animation: rotate 1.5s linear infinite; }
.auth-submit { width: 100%; }
.auth-note { border-top: 1px solid var(--color-border); margin: 28px 0 0; padding-top: 20px; font-size: 12px; text-align: center; color: var(--color-text-muted); }
.auth-footer { font-size: 12px; color: var(--color-text-muted); text-align: center; }
@keyframes rotate { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .entry-loading { animation: none; } }
@media (max-width: 900px) { .auth-layout { grid-template-columns: minmax(0,1fr); gap: 32px; margin-block: 40px; max-width: 480px; margin-inline: auto; } .auth-intro { display: none; } }
@media (max-width: 480px) { .auth-page { padding: 24px 16px; } .auth-card { padding: 24px 20px; } .auth-brand > span { gap: 12px; } }
</style>
