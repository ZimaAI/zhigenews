<script setup lang="ts">
import { useRouter } from 'vue-router';
import { api } from '@shared/mock';
const router = useRouter();
async function logout() {
  const failure = await router.push('/login');
  if (!failure) api.logout();
}
</script>

<template>
  <div class="user-form personal-settings">
    <header class="settings-header"><h1>个人设置</h1><button class="button button--ghost logout-button" @click="logout">退出登录</button></header>
    <nav class="tabs settings-tabs" aria-label="个人设置">
      <RouterLink to="/settings/preferences">兴趣订阅</RouterLink>
      <RouterLink to="/settings/schedule">推送时间</RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.personal-settings { max-width: 640px; }
.settings-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.settings-header h1 { margin: 0; }
.logout-button { color: var(--color-text-muted); font-size: 13px; padding-inline: 0; min-height: 44px; }
.settings-tabs { margin-bottom: 32px; gap: 28px; }
.settings-tabs a { min-height: 48px; }
</style>
