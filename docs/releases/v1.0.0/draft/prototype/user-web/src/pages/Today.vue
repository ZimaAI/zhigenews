<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ArrowUpRight, RefreshCw } from 'lucide-vue-next';
import { api, state } from '@shared/mock';
import EmptyState from '@shared/EmptyState.vue';
import NewsArticle from '../components/NewsArticle.vue';
const brief = computed(() => state.briefs[0]);
const hasSubscription = computed(() => state.preferences.topics.length > 0 || state.preferences.keywords.length > 0);
const activeRun = computed(() => state.runs.find((r) => r.userName === state.users[0]?.name && ['queued', 'running', 'cancelling'].includes(r.status)));
const selectedTopic = ref('全部');
const unread = ref(false);
const topics = computed(() => [...new Set(brief.value?.items.map((i) => i.topic) || [])]);
const items = computed(() => (brief.value?.items || []).filter((i) => (selectedTopic.value === '全部' || selectedTopic.value === i.topic) && (!unread.value || !i.read)));
const busy = ref(false), error = ref('');
watch(() => brief.value?.id, () => { selectedTopic.value = '全部'; });
async function generate() { if (busy.value || activeRun.value) return; busy.value = true; error.value = ''; try { await api.generateBrief(); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><h1>今日简报</h1><p v-if="brief" class="meta">{{ brief.date }} · {{ brief.items.length }} 条新闻</p></div><button class="button button--primary" :disabled="busy || !!activeRun || !hasSubscription" @click="generate"><RefreshCw :size="16" aria-hidden="true" />{{ busy ? '正在创建…' : activeRun ? '正在整理…' : '更新简报' }}</button></header>
    <div v-if="error" class="alert alert--danger" role="alert">{{ error }} <button class="button button--ghost" :disabled="busy" @click="generate">重试</button></div>
    <div v-if="activeRun" class="run-strip" role="status"><span class="user-loading-dot" aria-hidden="true"></span><span>{{ activeRun.status === 'cancelling' ? '正在取消…' : '简报整理中' }}</span><RouterLink :to="`/runs/${activeRun.id}`">查看进度<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></div>
    <EmptyState v-if="!hasSubscription" title="选择你关注的话题"><RouterLink class="button button--primary" to="/settings">设置订阅</RouterLink></EmptyState>
    <EmptyState v-else-if="!brief" title="还没有简报"><button class="button button--primary" :disabled="busy || !!activeRun" @click="generate">{{ activeRun ? '正在整理…' : '生成第一份简报' }}</button></EmptyState>
    <template v-else>
      <div v-if="brief.generationStatus === 'partial'" class="alert">部分来源暂不可用。<RouterLink :to="`/runs/${brief.runId}`">查看详情</RouterLink></div>
      <div v-if="brief.items.length" class="feed-toolbar"><div class="topic-tabs" role="group" aria-label="按话题筛选新闻"><button v-for="topic in ['全部', ...topics]" :key="topic" :aria-pressed="selectedTopic === topic" :class="{ selected: selectedTopic === topic }" @click="selectedTopic = topic">{{ topic }}</button></div><label class="unread-filter"><input v-model="unread" type="checkbox" />只看未读</label></div>
      <section v-if="items.length" class="news-list" aria-label="本期新闻"><NewsArticle v-for="item in items" :key="item.id" :item="item" :brief-id="brief.id" /></section>
      <EmptyState v-else-if="!brief.items.length" title="本期没有匹配的新闻"><RouterLink class="button" to="/settings">调整订阅</RouterLink></EmptyState>
      <EmptyState v-else title="没有符合筛选的新闻"><button class="button" @click="selectedTopic = '全部'; unread = false">清除筛选</button></EmptyState>
      <footer v-if="brief.items.length" class="feed-end"><RouterLink :to="`/briefs/${brief.id}`">阅读整期<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></footer>
    </template>
  </div>
</template>
<style scoped>
.run-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 12px 16px; background: var(--color-primary-soft); border-radius: var(--radius-control); margin-bottom: 24px; font-size: 13px; }
.run-strip a { display: inline-flex; align-items: center; gap: 4px; margin-left: auto; }
.feed-toolbar { display: flex; align-items: center; gap: 24px; border-bottom: 1px solid var(--color-border); }
.topic-tabs { display: flex; align-items: center; gap: 20px; min-width: 0; overflow-x: auto; }
.topic-tabs button { white-space: nowrap; background: none; border: 0; border-bottom: 2px solid transparent; padding: 10px 0; min-height: 44px; color: var(--color-text-muted); font: inherit; font-size: 14px; }
.topic-tabs button.selected { color: var(--color-primary); border-bottom-color: var(--color-primary); font-weight: 600; }
.unread-filter { margin-left: auto; white-space: nowrap; display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; color: var(--color-text-secondary); cursor: pointer; }
.unread-filter input { accent-color: var(--color-primary); width: 16px; height: 16px; }
.feed-end { display: flex; justify-content: center; padding-top: 24px; border-top: 1px solid var(--color-border); }
.feed-end a { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; min-height: 44px; }
@media (max-width: 767px) { .feed-toolbar { flex-wrap: wrap; gap: 0; } .topic-tabs { flex: 1 1 100%; gap: 16px; } .unread-filter { margin-left: 0; } }
</style>
