<script setup lang="ts">
import { Clock3, Rss, UserRound } from 'lucide-vue-next';
</script>

<template>
  <div class="user-form personal-settings">
    <header class="settings-header"><h1>个人设置</h1><span class="anonymous-label"><UserRound :size="15" aria-hidden="true" />匿名账户</span></header>
    <nav class="tabs settings-tabs" aria-label="个人设置">
      <RouterLink to="/settings/preferences"><Rss :size="17" :stroke-width="1.8" aria-hidden="true" />兴趣订阅</RouterLink>
      <RouterLink to="/settings/schedule"><Clock3 :size="17" :stroke-width="1.8" aria-hidden="true" />推送时间</RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.personal-settings { max-width: 640px; }
.settings-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.settings-header h1 { margin: 0; }
.anonymous-label { display: inline-flex; align-items: center; gap: 6px; color: var(--color-text-muted); font-size: 13px; padding-inline: 0; min-height: 44px; }
.settings-tabs { margin-bottom: 32px; gap: 28px; }
.settings-tabs a { display: inline-flex; align-items: center; gap: 8px; min-height: 48px; }
</style>
