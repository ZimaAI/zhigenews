<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { LockKeyhole, ArrowRight } from 'lucide-vue-next';
import { api, notify } from '@shared/mock';
const router = useRouter(); const email = ref('admin@example.com'); const password = ref('demo-admin'); const role = ref('admin'); const busy = ref(false); const error = ref('');
async function submit() { busy.value = true; error.value = ''; try { if (role.value !== 'admin') throw new Error('403 FORBIDDEN（模拟）：普通用户不能访问管理控制台。请切换为管理员演示身份。'); await api.login(email.value, password.value); notify('已进入管理员演示会话。'); router.push('/overview'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template><div class="admin-auth"><div class="eyebrow">ZHIGENEWS / ADMIN</div><h1>管理控制台</h1><p class="muted">把内容、模型与每一次运行管理清楚。</p><form class="card stack admin-form" @submit.prevent="submit"><div class="row"><LockKeyhole :size="20" class="admin-mini-icon" /><h2>管理员登录</h2></div><p class="alert">仅用于交互原型。使用预填的演示凭据，不提交真实密码。</p><p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p><label class="field">演示身份<select v-model="role" class="field-control"><option value="admin">管理员 · 可访问</option><option value="user">普通用户 · 模拟权限拒绝</option></select></label><label class="field">邮箱<input v-model="email" class="field-control" type="email" required autocomplete="off"></label><label class="field">演示密码<input v-model="password" class="field-control" type="password" required minlength="6" autocomplete="off"></label><button class="button button--primary" :disabled="busy" type="submit">{{ busy ? '正在验证…' : '进入管理控制台' }}<ArrowRight :size="16" /></button><p class="meta">正式系统的角色校验由后端执行；本页面只演示 403 拒绝语义。</p></form></div></template>
