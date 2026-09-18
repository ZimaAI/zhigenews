<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowRight, SlidersHorizontal, WandSparkles, ArrowUpRight, CalendarDays } from 'lucide-vue-next';
import { api, state, formatDate } from '@shared/mock';
import EmptyState from '@shared/EmptyState.vue';
import Badge from '@shared/Badge.vue';
import NewsArticle from '../components/NewsArticle.vue';
const brief = computed(() => state.briefs[0]);
const hasSubscription = computed(() => state.preferences.topics.length > 0 || state.preferences.keywords.length > 0);
const subscriptionSummary = computed(() => [...new Set([...state.preferences.topics, ...state.preferences.keywords])].join('、'));
const activeRun = computed(() => state.runs.find((r) => ['queued', 'running', 'cancelling'].includes(r.status)));
const selectedTopic = ref('全部');
const unread = ref(false);
const topics = computed(() => [...new Set(brief.value?.items.map((i) => i.topic) || [])]);
const items = computed(() => (brief.value?.items || []).filter((i) => (selectedTopic.value === '全部' || selectedTopic.value === i.topic) && (!unread.value || !i.read)));
const busy = ref(false), error = ref('');
async function generate() { if (busy.value || activeRun.value) return; busy.value = true; error.value = ''; try { await api.generateBrief(); } catch (e) { error.value = (e as Error).message; } finally { busy.value = false; } }
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><p class="eyebrow">YOUR DAILY BRIEF</p><h1>今日简报</h1><p class="muted">把关注的变化，留在每天的阅读里。</p></div><button class="button button--primary" :disabled="busy || !!activeRun || !hasSubscription" @click="generate"><WandSparkles :size="16" aria-hidden="true" />{{ busy ? '正在创建…' : activeRun ? '正在整理…' : '生成新简报' }}</button></header>
    <div v-if="error" class="alert alert--danger" role="alert">{{ error }} <button class="button button--ghost" :disabled="busy" @click="generate">重试生成</button></div>
    <div v-if="activeRun" class="run-strip"><span class="user-loading-dot" aria-hidden="true"></span><span>正在整理与你关注主题有关的内容，现有简报仍可阅读。</span><RouterLink :to="`/runs/${activeRun.id}`">查看模拟过程<ArrowUpRight :size="14" aria-hidden="true" /></RouterLink></div>
    <EmptyState v-if="!hasSubscription" title="先告诉我们你关注什么" description="选择主题或添加关键词，让每一份简报更贴近你的工作与兴趣。"><RouterLink class="button button--primary" to="/onboarding">设置兴趣订阅<ArrowRight :size="16" aria-hidden="true" /></RouterLink></EmptyState>
    <EmptyState v-else-if="!brief" title="第一份简报还未生成" :description="`你已关注 ${subscriptionSummary}。生成后，内容会保留在这里。`"><button class="button button--primary" :disabled="busy || !!activeRun" @click="generate">{{ activeRun ? '正在生成模拟简报…' : '生成第一份简报' }}</button></EmptyState>
    <template v-else>
      <section class="brief-intro"><div class="intro-date"><CalendarDays :size="16" aria-hidden="true" /><span>{{ brief.date }}</span><span class="intro-divider">/</span><span>{{ brief.items.length }} 条精选 · 示例内容</span><RouterLink :to="`/briefs/${brief.id}`" class="intro-link">阅读整期<ArrowUpRight :size="15" aria-hidden="true" /></RouterLink></div><h2>{{ brief.title }}</h2><p>{{ brief.summary }}</p><div class="intro-footer"><div class="user-status-line"><strong>内容</strong><Badge :status="brief.generationStatus" /><strong>邮件</strong><Badge :status="brief.deliveryStatus" /></div><span class="meta">生成于 {{ formatDate(brief.generatedAt) }}</span></div></section>
      <div v-if="brief.generationStatus === 'partial'" class="alert partial-alert">部分来源暂不可用，以下保留已完成内容。<RouterLink :to="`/runs/${brief.runId}`">查看缺失原因</RouterLink></div>
      <div v-if="brief.items.length" class="feed-toolbar"><div class="topic-tabs" role="group" aria-label="按主题筛选新闻"><button v-for="topic in ['全部', ...topics]" :key="topic" :aria-pressed="selectedTopic === topic" :class="{ selected: selectedTopic === topic }" @click="selectedTopic = topic">{{ topic }}<span v-if="topic === '全部'">{{ brief.items.length }}</span></button></div><label class="unread-filter"><input v-model="unread" type="checkbox" />只看未读</label></div>
      <section v-if="items.length" class="news-list" aria-label="本期新闻"><NewsArticle v-for="item in items" :key="item.id" :item="item" :brief-id="brief.id" /></section>
      <EmptyState v-else-if="!brief.items.length" title="本期没有符合订阅的内容" description="当前范围内没有匹配结果，系统没有自动放宽规则。可以调整关键词、排除项或新闻时间范围后重新生成。"><RouterLink class="button button--primary" to="/preferences">调整兴趣订阅</RouterLink></EmptyState><EmptyState v-else title="当前筛选下没有内容" description="可切换主题，或关闭“只看未读”查看本期其他内容。"><button class="button" @click="selectedTopic = '全部'; unread = false">清除筛选</button></EmptyState>
      <footer v-if="brief.items.length" class="feed-end"><span class="end-line"></span><span>本期阅读到这里</span><span class="end-line"></span></footer>
      <section class="preference-footer"><SlidersHorizontal :size="18" aria-hidden="true" /><div><strong>让下一份更合心意</strong><p class="meta">当前关注 {{ subscriptionSummary }} · {{ state.preferences.windowHours }} 小时内 · 最多 {{ state.preferences.maxItems }} 条</p></div><RouterLink to="/preferences" class="button button--ghost">调整订阅<ArrowRight :size="15" aria-hidden="true" /></RouterLink></section>
    </template>
  </div>
</template>
<style scoped>
.run-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid var(--color-primary-border); background: var(--color-primary-soft); border-radius: 8px; margin-bottom: 24px; font-size: 13px; }
.run-strip a { display: inline-flex; align-items: center; gap: 4px; margin-left: auto; }
.brief-intro { padding: 24px; border: 1px solid var(--color-border); border-radius: 12px; background: var(--color-surface); }
.intro-date { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 13px; color: var(--color-text-muted); }
.intro-divider { margin-inline: 4px; color: var(--color-border-control); }
.intro-link { display: flex; align-items: center; gap: 4px; margin-left: auto; text-decoration: none; }
.brief-intro h2 { font-size: 20px; line-height: 30px; margin: 20px 0 8px; font-weight: 600; }
.brief-intro > p { margin: 0; line-height: 26px; color: var(--color-text-secondary); }
.intro-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding-top: 20px; margin-top: 20px; border-top: 1px solid var(--color-border); }
.partial-alert { margin-top: 16px; }
.feed-toolbar { display: flex; align-items: center; gap: 16px; margin-block: 24px 16px; }
.topic-tabs { display: flex; align-items: center; gap: 20px; min-width: 0; overflow-x: auto; }
.topic-tabs button { display: flex; align-items: center; gap: 8px; white-space: nowrap; background: none; border: 0; border-bottom: 2px solid transparent; padding: 8px 0; min-height: 44px; color: var(--color-text-muted); font: inherit; font-size: 14px; cursor: pointer; }
.topic-tabs button.selected { color: var(--color-primary); border-bottom-color: var(--color-primary); font-weight: 600; }
.topic-tabs button span { font-size: 11px; padding: 0 6px; background: var(--color-surface-muted); border-radius: 4px; }
.unread-filter { margin-left: auto; white-space: nowrap; display: flex; align-items: center; gap: 8px; font-size: 13px; min-height: 44px; color: var(--color-text-secondary); cursor: pointer; }
.unread-filter input { accent-color: var(--color-primary); width: 16px; height: 16px; }
.news-list { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; overflow: hidden; }
.feed-end { display: flex; align-items: center; justify-content: center; gap: 16px; color: var(--color-text-muted); font-size: 12px; margin: 32px auto; max-width: 320px; }
.end-line { flex: 1; height: 1px; background: var(--color-border); }
.preference-footer { display: flex; align-items: center; gap: 16px; margin-top: 16px; padding-bottom: 16px; }
.preference-footer > svg { color: var(--color-text-muted); flex-shrink: 0; }
.preference-footer strong { font-size: 14px; font-weight: 500; }
.preference-footer p { margin: 4px 0 0; }
.preference-footer .button { margin-left: auto; white-space: nowrap; }
@media (max-width: 767px) { .brief-intro { padding: 20px 16px; } .feed-toolbar { flex-wrap: wrap; gap: 4px; } .topic-tabs { flex: 1 1 100%; gap: 16px; } .unread-filter { margin-left: 0; } .preference-footer { flex-wrap: wrap; align-items: flex-start; gap: 12px; } .preference-footer > div { flex: 1; min-width: 0; } .preference-footer .button { margin-left: 30px; } }
</style>
