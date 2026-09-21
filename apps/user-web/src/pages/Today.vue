<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ArrowUpRight, WandSparkles, CalendarDays, LayoutGrid, Hash, BookOpen } from 'lucide-vue-next';
import { api, ApiError, type Brief, type BriefPage, type Preferences, type GenerationProgress as Progress } from '@zhigenews/api-client';
import EmptyState from '@ui/EmptyState.vue';
import NewsArticle from '../components/NewsArticle.vue';
import GenerationProgress from '../components/GenerationProgress.vue';
import LoadingState from '../components/LoadingState.vue';
import { useRequestState } from '../useRequestState';
import { useGeneration } from '../useGeneration';
const brief = ref<Brief | null>(null), preferences = ref<Preferences | null>(null);
const loading = ref(true), busy = ref(false), selectedTopic = ref('全部');
const { error, remaining, fail, clear } = useRequestState();
const { progress, reconnecting, accept: updateProgress, poll } = useGeneration(brief, exception => { retryAction = poll; fail(exception); });
const hasSubscription = computed(() => !!preferences.value && !!(preferences.value.topics.length || preferences.value.keywords.length));
const generating = computed(() => reconnecting.value || !!progress.value && ['queued', 'running', 'cancelling'].includes(progress.value.status));
const topics = computed(() => [...new Set(brief.value?.items.map(item => item.topic) || [])]);
const items = computed(() => (brief.value?.items || []).filter(item => selectedTopic.value === '全部' || selectedTopic.value === item.topic));
const controller = new AbortController();
let pendingIntent: { key: string; preferenceVersion: number } | null = null;
let retryAction: () => Promise<void> = load;
watch(() => brief.value?.id, () => { selectedTopic.value = '全部'; });
onBeforeUnmount(() => { controller.abort(); });
async function load() {
  if (remaining.value) return;
  clear(); retryAction = load;
  try {
    const [pref, page] = await Promise.all([
      api<Preferences>('getPreferences', { signal: controller.signal }),
      api<BriefPage>('listBriefs', { query: { limit: 1 }, signal: controller.signal }),
    ]);
    preferences.value = pref; brief.value = page.items[0] || null;
    await poll();
  } catch (exception) { if (!controller.signal.aborted) fail(exception); }
  finally { loading.value = false; }
}
async function generate() {
  if (busy.value || generating.value || remaining.value || !preferences.value) return;
  busy.value = true; clear(); retryAction = generate;
  pendingIntent ??= { key: crypto.randomUUID(), preferenceVersion: preferences.value.version };
  try {
    const value = await api<Progress>('generateBrief', { body: { preferenceVersion: pendingIntent.preferenceVersion }, idempotencyKey: pendingIntent.key, signal: controller.signal });
    pendingIntent = null; await updateProgress(value);
  } catch (exception) {
    if (!controller.signal.aborted) {
      fail(exception instanceof ApiError && [401, 403, 409, 429].includes(exception.status)
        ? exception : new Error('暂时无法提交，请重试'));
      if (exception instanceof ApiError && exception.status >= 400 && exception.status < 500) {
        pendingIntent = null;
        if (exception.code === 'VERSION_CONFLICT' || exception.code === 'INVALID_STATE') retryAction = load;
      }
    }
  } finally { busy.value = false; }
}
async function cancel() {
  if (busy.value || !progress.value || !generating.value || remaining.value) return;
  busy.value = true; clear(); retryAction = cancel;
  try { await updateProgress(await api<Progress>('cancelGeneration', { path: { id: progress.value.id }, signal: controller.signal })); }
  catch (exception) { if (!controller.signal.aborted) fail(exception); }
  finally { busy.value = false; }
}
async function retry() { if (remaining.value) return; clear(); await retryAction(); }
onMounted(load);
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><h1>今日简报</h1><p v-if="brief" class="brief-meta meta"><span><CalendarDays :size="14" :stroke-width="1.8" aria-hidden="true" />{{ brief.date }}</span><span class="badge">{{ brief.items.length }} 条新闻</span></p></div><button class="button button--primary" :disabled="loading || busy || generating || !hasSubscription || remaining > 0" @click="generate"><WandSparkles :size="16" :stroke-width="1.8" aria-hidden="true" />{{ busy || generating ? '正在生成…' : '更新简报' }}</button></header>
    <div v-if="error" class="alert alert--danger" role="alert"><span>{{ error }}</span><button class="button button--ghost" :disabled="busy || remaining > 0" @click="retry">{{ remaining ? `${remaining} 秒后可重试` : '重试' }}</button></div>
    <LoadingState v-if="loading" />
    <template v-else>
      <GenerationProgress v-if="progress || reconnecting" :progress="progress" :reconnecting="reconnecting" :busy="busy || remaining > 0" @cancel="cancel" @retry="generate" />
      <EmptyState v-if="!preferences && !brief" error title="暂时无法读取简报" description="恢复连接后重试加载。" />
      <EmptyState v-else-if="!hasSubscription" title="选择你关注的话题"><RouterLink class="button button--primary" to="/settings">设置订阅</RouterLink></EmptyState>
      <EmptyState v-else-if="!brief" title="还没有简报"><button class="button button--primary" :disabled="busy || generating || remaining > 0" @click="generate">{{ generating ? '正在生成…' : '生成第一份简报' }}</button></EmptyState>
      <template v-else>
        <div v-if="brief.items.length" class="feed-toolbar"><div class="topic-tabs" role="group" aria-label="按话题筛选新闻"><button v-for="topic in ['全部', ...topics]" :key="topic" :aria-pressed="selectedTopic === topic" :class="{ selected: selectedTopic === topic }" @click="selectedTopic = topic"><component :is="topic === '全部' ? LayoutGrid : Hash" :size="14" :stroke-width="1.8" aria-hidden="true" />{{ topic }}</button></div></div>
        <section v-if="items.length" class="news-list" aria-label="本期新闻"><NewsArticle v-for="item in items" :key="item.id" :item="item" /></section>
        <EmptyState v-else-if="!brief.items.length" title="本期没有匹配的新闻"><RouterLink class="button" to="/settings">调整订阅</RouterLink></EmptyState>
        <EmptyState v-else title="没有符合筛选的新闻"><button class="button" @click="selectedTopic = '全部'">清除筛选</button></EmptyState>
        <footer v-if="brief.items.length" class="feed-end"><RouterLink :to="`/briefs/${brief.id}`"><BookOpen :size="16" :stroke-width="1.8" aria-hidden="true" />阅读整期<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></footer>
      </template>
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
