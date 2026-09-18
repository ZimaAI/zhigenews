<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowRight, Feather, Eye, EyeOff } from 'lucide-vue-next';
import { api } from '@shared/mock';
const route = useRoute(), router = useRouter();
const registering = computed(() => route.path === '/register');
const form = reactive({ name: '', email: 'reader@example.com', password: 'demo12345' });
const busy = ref(false), error = ref(''), reveal = ref(false);
async function submit() { if (busy.value) return; busy.value = true; error.value = ''; try { if (registering.value) await api.register(form.email, form.password, form.name); else await api.login(form.email, form.password); await router.push(registering.value ? '/onboarding' : '/today'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <main class="auth-page"><a class="skip-auth" href="#auth-form">跳转到登录表单</a><div class="auth-brand"><Feather :size="28" aria-hidden="true" /><span>知更<span class="brand-en">QUIET BRIEF</span></span></div><div class="auth-layout"><section class="auth-intro"><p class="eyebrow">LESS NOISE. MORE SIGNAL.</p><h1>每天，读一点<br />真正关心的事。</h1><p>订阅你的兴趣，让 Agent 从热榜、RSS 与网络搜索中整理一份有来源的 AI 新闻简报。</p><div class="auth-preview"><span class="meta">交互原型 · 示例数据</span><p>你的兴趣，你的阅读节奏。</p><span class="meta">不连接真实账户，不发送邮件，不调用付费模型。</span></div></section><section class="auth-card"><h2>{{ registering ? '创建你的阅读空间' : '欢迎回来' }}</h2><p class="muted">{{ registering ? '使用演示账户体验首次配置流程。' : '登录演示账户，继续今天的阅读。' }}</p><p v-if="error" class="alert alert--danger" role="alert">{{ error }} 输入已保留，可重试。</p><form id="auth-form" @submit.prevent="submit"><div v-if="registering" class="field"><label for="display-name">称呼</label><input id="display-name" v-model="form.name" class="field-control" autocomplete="nickname" maxlength="40" required placeholder="如何称呼你" /></div><div class="field"><label for="email">邮箱</label><input id="email" v-model="form.email" class="field-control" type="email" autocomplete="username" required /></div><div class="field"><label for="password">密码</label><div class="password-field"><input id="password" v-model="form.password" class="field-control" :type="reveal ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" required minlength="8" /><button type="button" :aria-label="reveal ? '隐藏密码' : '显示密码'" @click="reveal = !reveal"><EyeOff v-if="reveal" :size="18" /><Eye v-else :size="18" /></button></div><span class="meta">至少 8 个字符。请勿输入真实密码。</span></div><button class="button button--primary auth-submit" :disabled="busy" type="submit">{{ busy ? '正在进入…' : registering ? '模拟创建账户' : '进入演示账户' }}<ArrowRight :size="16" aria-hidden="true" /></button></form><p class="auth-switch">{{ registering ? '已有账户？' : '第一次来？' }}<RouterLink :to="registering ? '/login' : '/register'" @click="error = ''">{{ registering ? '去登录' : '创建演示账户' }}</RouterLink></p><p class="meta auth-note">{{ registering ? '此操作仅创建本地演示状态，不建立真实服务端账户。' : '预填的是公开演示凭据，仅用于查看原型。' }}</p></section></div><footer class="auth-footer">知更 · 安静的个性化新闻阅读器</footer></main>
</template>
<style scoped>
.auth-page { max-width: 1200px; margin: auto; padding: 40px; min-height: 100vh; }
.skip-auth { position: absolute; left: -10000px; }
.skip-auth:focus { left: 20px; top: 8px; }
.auth-brand { display: inline-flex; align-items: center; gap: 12px; color: var(--color-primary); font-size: 24px; font-weight: 600; }
.auth-brand > span { display: flex; align-items: center; gap: 16px; }
.brand-en { color: var(--color-text-muted); font-size: 11px; font-weight: 500; letter-spacing: 2px; }
.auth-layout { display: grid; grid-template-columns: 1fr 420px; align-items: center; gap: 80px; margin-block: 88px 80px; }
.auth-intro h1 { font-size: 40px; line-height: 56px; margin: 20px 0; font-weight: 600; }
.auth-intro > p:not(.eyebrow) { font-size: 16px; line-height: 28px; max-width: 380px; color: var(--color-text-secondary); }
.auth-preview { margin-top: 40px; padding-left: 20px; border-left: 2px solid var(--color-primary-border); }
.auth-preview p { margin: 8px 0; font-size: 16px; }
.auth-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; padding: 32px; }
.auth-card h2 { margin: 0 0 8px; font-size: 24px; }
.auth-card > .muted { margin: 0 0 24px; font-size: 14px; }
.auth-card .field { margin-bottom: 20px; }
.password-field { display: flex; position: relative; }
.password-field input { padding-right: 44px; }
.password-field button { border: 0; background: none; position: absolute; right: 0; top: 0; display: flex; align-items: center; justify-content: center; height: 44px; width: 44px; color: var(--color-text-muted); cursor: pointer; }
.auth-submit { width: 100%; margin-top: 4px; }
.auth-switch { font-size: 14px; text-align: center; margin: 24px 0; }
.auth-switch a { margin-left: 8px; }
.auth-note { border-top: 1px solid var(--color-border); margin: 0; padding-top: 20px; text-align: center; }
.auth-footer { font-size: 12px; color: var(--color-text-muted); text-align: center; }
@media (max-width: 900px) { .auth-layout { grid-template-columns: minmax(0, 1fr); gap: 32px; margin-block: 40px; max-width: 480px; margin-inline: auto; } .auth-intro h1 { font-size: 30px; line-height: 42px; } .auth-intro { display: none; } }
@media (max-width: 480px) { .auth-page { padding: 24px 16px; } .auth-card { padding: 24px 20px; } .auth-brand > span { gap: 12px; } }
</style>
