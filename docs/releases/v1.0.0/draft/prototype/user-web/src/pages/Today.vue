<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ArrowUpRight, WandSparkles, CalendarDays, LayoutGrid, Hash, BookOpen } from 'lucide-vue-next';
import { api, state } from '@shared/mock';
import EmptyState from '@shared/EmptyState.vue';
import NewsArticle from '../components/NewsArticle.vue';
import GenerationProgress from '../components/GenerationProgress.vue';
const brief = computed(() => state.briefs[0]);
const hasSubscription = computed(() => state.preferences.topics.length > 0 || state.preferences.keywords.length > 0);
const generating = computed(() => !!state.generation && ['queued', 'running', 'cancelling'].includes(state.generation.status));
const selectedTopic = ref('全部');
const topics = computed(() => [...new Set(brief.value?.items.map((i) => i.topic) || [])]);
const items = computed(() => (brief.value?.items || []).filter((i) => selectedTopic.value === '全部' || selectedTopic.value === i.topic));
const busy = ref(false), error = ref('');
watch(() => brief.value?.id, () => { selectedTopic.value = '全部'; });
async function generate() { if (busy.value || generating.value) return; busy.value = true; error.value = ''; try { await api.generateBrief(); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
async function cancel() { if (busy.value || !generating.value) return; busy.value = true; error.value = ''; try { await api.cancelGeneration(); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><h1>今日简报</h1><p v-if="brief" class="brief-meta meta"><span><CalendarDays :size="14" :stroke-width="1.8" aria-hidden="true" />{{ brief.date }}</span><span class="badge">{{ brief.items.length }} 条新闻</span></p></div><button class="button button--primary" :disabled="busy || generating || !hasSubscription" @click="generate"><WandSparkles :size="16" :stroke-width="1.8" aria-hidden="true" />{{ busy || generating ? '正在生成…' : '更新简报' }}</button></header>
    <div v-if="error" class="alert alert--danger" role="alert">{{ error }} <button class="button button--ghost" :disabled="busy" @click="generating ? cancel() : generate()">重试</button></div>
    <GenerationProgress v-if="state.generation" :progress="state.generation" :busy="busy" @cancel="cancel" @retry="generate" />
    <EmptyState v-if="!hasSubscription" title="选择你关注的话题"><RouterLink class="button button--primary" to="/settings">设置订阅</RouterLink></EmptyState>
    <EmptyState v-else-if="!brief" title="还没有简报"><button class="button button--primary" :disabled="busy || generating" @click="generate">{{ generating ? '正在生成…' : '生成第一份简报' }}</button></EmptyState>
    <template v-else>
      <div v-if="brief.generationStatus === 'partial' && state.generation?.briefId !== brief.id" class="alert">部分来源暂不可用，已保留完成的内容。</div>
      <div v-if="brief.items.length" class="feed-toolbar"><div class="topic-tabs" role="group" aria-label="按话题筛选新闻"><button v-for="topic in ['全部', ...topics]" :key="topic" :aria-pressed="selectedTopic === topic" :class="{ selected: selectedTopic === topic }" @click="selectedTopic = topic"><component :is="topic === '全部' ? LayoutGrid : Hash" :size="14" :stroke-width="1.8" aria-hidden="true" />{{ topic }}</button></div></div>
      <section v-if="items.length" class="news-list" aria-label="本期新闻"><NewsArticle v-for="item in items" :key="item.id" :item="item" /></section>
      <EmptyState v-else-if="!brief.items.length" title="本期没有匹配的新闻"><RouterLink class="button" to="/settings">调整订阅</RouterLink></EmptyState>
      <EmptyState v-else title="没有符合筛选的新闻"><button class="button" @click="selectedTopic = '全部'">清除筛选</button></EmptyState>
      <footer v-if="brief.items.length" class="feed-end"><RouterLink :to="`/briefs/${brief.id}`"><BookOpen :size="16" :stroke-width="1.8" aria-hidden="true" />阅读整期<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></footer>
    </template>
  </div>
</template>
<style scoped>
.brief-meta, .brief-meta > span { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.brief-meta { gap: 12px; }
.feed-toolbar { display: flex; align-items: center; gap: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.topic-tabs { display: flex; align-items: center; gap: 8px; min-width: 0; overflow-x: auto; padding: 4px; margin-left: -4px; }
.topic-tabs button { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; background: none; border: 1px solid transparent; border-radius: var(--radius-pill); padding: 8px 12px; min-height: 44px; color: var(--color-text-muted); font: inherit; font-size: 14px; }
.topic-tabs button:hover { color: var(--color-primary); background: var(--color-surface-muted); }
.topic-tabs button.selected { color: var(--color-primary); border-color: var(--color-primary-border); background: var(--color-primary-soft); font-weight: 600; }
.feed-end { display: flex; justify-content: center; padding-top: 24px; border-top: 1px solid var(--color-border); }
.feed-end a { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; min-height: 44px; }
@media (max-width: 767px) { .feed-toolbar { flex-wrap: wrap; gap: 0; } .topic-tabs { flex: 1 1 100%; } }
</style>
