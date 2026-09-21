<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import BrandLogo from '@ui/BrandLogo.vue';
import { ArrowRight } from 'lucide-vue-next';
import type { AdminSession } from '@zhigenews/api-client';
import { request, errorText } from '../lib';
import { session } from '../session';
const route = useRoute(); const router = useRouter(); const email = ref(''); const password = ref(''); const error = ref(''); const busy = ref(false);
async function login() {
  if (busy.value) return; busy.value = true; error.value = '';
  try { session.value = await request<AdminSession>('adminLogin', { body: { email: email.value.trim(), password: password.value } }); password.value = ''; const redirect = String(route.query.redirect || '/overview'); await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') && !redirect.startsWith('/login') ? redirect : '/overview'); }
  catch (err) { error.value = errorText(err); }
  finally { busy.value = false; }
}
</script>
<template><div class="admin-auth"><div class="row admin-login-brand"><BrandLogo decorative /><strong>知更 · 管理控制台</strong></div><section class="card"><div class="eyebrow">WELCOME BACK</div><h1>管理员登录</h1><p class="muted">使用管理员账户进入工作台。</p><form class="stack admin-section" @submit.prevent="login"><p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p><label class="field">邮箱<input v-model="email" class="field-control" type="email" autocomplete="username" required autofocus :disabled="busy" placeholder="输入管理员邮箱"></label><label class="field">密码<input v-model="password" class="field-control" type="password" autocomplete="current-password" required :disabled="busy"></label><button class="button button--primary" type="submit" :disabled="busy">{{ busy ? '正在登录…' : '登录控制台' }}<ArrowRight :size="16" /></button></form></section><p class="meta admin-section">管理员账户由部署负责人配置。用户端匿名账户无法登录管理控制台。</p></div></template>
