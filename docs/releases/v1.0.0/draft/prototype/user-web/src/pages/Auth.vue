<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { BookOpen, Eye, EyeOff } from 'lucide-vue-next';
import { api } from '@shared/mock';
const route = useRoute(), router = useRouter();
const registering = computed(() => route.path === '/register');
const form = reactive({ name: '', email: 'reader@example.com', password: 'demo12345' });
const busy = ref(false), error = ref(''), reveal = ref(false);
async function submit() { if (busy.value) return; busy.value = true; error.value = ''; try { if (registering.value) await api.register(form.email, form.password, form.name); else await api.login(form.email, form.password); await router.push(registering.value ? '/onboarding' : '/today'); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <main class="auth-page">
    <a class="skip-auth" href="#auth-form">跳转到表单</a>
    <div class="auth-brand"><BookOpen :size="26" aria-hidden="true" /><span>知更</span></div>
    <section class="auth-card">
      <h1>{{ registering ? '创建账户' : '欢迎回来' }}</h1>
      <p v-if="error" class="alert alert--danger" role="alert">{{ error }}</p>
      <form id="auth-form" @submit.prevent="submit">
        <div v-if="registering" class="field"><label for="display-name">称呼</label><input id="display-name" v-model="form.name" class="field-control" autocomplete="nickname" maxlength="40" required /></div>
        <div class="field"><label for="email">邮箱</label><input id="email" v-model="form.email" class="field-control" type="email" autocomplete="username" required /></div>
        <div class="field"><label for="password">密码</label><div class="password-field"><input id="password" v-model="form.password" class="field-control" :type="reveal ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" required minlength="8" placeholder="至少 8 个字符" /><button type="button" :aria-label="reveal ? '隐藏密码' : '显示密码'" @click="reveal = !reveal"><EyeOff v-if="reveal" :size="18" /><Eye v-else :size="18" /></button></div></div>
        <button class="button button--primary auth-submit" :disabled="busy" type="submit">{{ busy ? '正在进入…' : registering ? '创建账户' : '登录' }}</button>
      </form>
      <p class="auth-switch">{{ registering ? '已有账户？' : '还没有账户？' }}<RouterLink :to="registering ? '/login' : '/register'" @click="error = ''">{{ registering ? '登录' : '注册' }}</RouterLink></p>
    </section>
    <p class="auth-note">演示原型 · 使用预填的演示账户</p>
  </main>
</template>
<style scoped>
.auth-page { width: min(100%, 448px); margin: auto; padding: 64px 24px; min-height: 100vh; }
.skip-auth { position: absolute; left: -10000px; }
.skip-auth:focus { left: 20px; top: 8px; }
.auth-brand { display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--color-primary); font-size: 24px; font-weight: 600; margin-bottom: 36px; }
.auth-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-card); padding: 32px; }
.auth-card h1 { margin: 0 0 28px; font-size: 24px; }
.auth-card .field { margin-bottom: 24px; }
.password-field { display: flex; position: relative; }
.password-field input { padding-right: 44px; }
.password-field button { border: 0; background: none; position: absolute; right: 0; top: 0; display: flex; align-items: center; justify-content: center; height: 44px; width: 44px; color: var(--color-text-muted); cursor: pointer; }
.auth-submit { width: 100%; margin-top: 4px; }
.auth-switch { font-size: 14px; text-align: center; margin: 24px 0 0; }
.auth-switch a { display: inline-flex; align-items: center; margin-left: 8px; min-height: 44px; }
.auth-note { margin-top: 24px; text-align: center; color: var(--color-text-muted); font-size: 12px; }
@media (max-width: 480px) { .auth-page { padding: 40px 16px; } .auth-card { padding: 24px 20px; } }
</style>
