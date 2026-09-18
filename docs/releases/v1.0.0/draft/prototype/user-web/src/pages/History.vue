<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Search, ArrowUpRight, ChevronLeft, ChevronRight, X } from 'lucide-vue-next';
import { state, TOPICS } from '@shared/mock';
import Badge from '@shared/Badge.vue';
import EmptyState from '@shared/EmptyState.vue';
const route = useRoute(), router = useRouter();
const filters = reactive({ search: String(route.query.q || ''), topic: String(route.query.topic || ''), from: String(route.query.from || ''), to: String(route.query.to || ''), generation: String(route.query.generation || ''), delivery: String(route.query.delivery || ''), page: Number(route.query.page || 1), size: Number(route.query.size || 20) });
const matched = computed(() => state.briefs.filter((b) => (!filters.search || `${b.title} ${b.summary}`.toLowerCase().includes(filters.search.toLowerCase())) && (!filters.topic || b.items.some((i) => i.topic === filters.topic)) && (!filters.from || b.date >= filters.from) && (!filters.to || b.date <= filters.to) && (!filters.generation || b.generationStatus === filters.generation) && (!filters.delivery || b.deliveryStatus === filters.delivery)));
const pageCount = computed(() => Math.max(1, Math.ceil(matched.value.length / filters.size)));
const visible = computed(() => matched.value.slice((filters.page - 1) * filters.size, filters.page * filters.size));
const active = computed(() => !!(filters.search || filters.topic || filters.from || filters.to || filters.generation || filters.delivery));
watch(() => [filters.search, filters.topic, filters.from, filters.to, filters.generation, filters.delivery, filters.size], () => { filters.page = 1; });
watch(filters, () => { router.replace({ query: { q: filters.search || undefined, topic: filters.topic || undefined, from: filters.from || undefined, to: filters.to || undefined, generation: filters.generation || undefined, delivery: filters.delivery || undefined, page: filters.page > 1 ? filters.page : undefined, size: filters.size !== 20 ? filters.size : undefined } }); });
function clear() { Object.assign(filters, { search: '', topic: '', from: '', to: '', generation: '', delivery: '', page: 1 }); }
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><p class="eyebrow">YOUR READING ARCHIVE</p><h1>历史简报</h1><p class="muted">每一次整理，都为你留存。</p></div><RouterLink class="button" to="/today">回到今日<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink></header>
    <section class="history-filters card" aria-label="筛选历史简报"><div class="search-field"><Search :size="17" aria-hidden="true" /><label for="history-search" class="sr-only">搜索历史简报</label><input id="history-search" v-model="filters.search" class="field-control" type="search" placeholder="搜索历史简报标题与摘要" /></div><div class="filter-grid"><div class="field"><label for="from">起始日期</label><input id="from" v-model="filters.from" class="field-control" type="date" /></div><div class="field"><label for="to">结束日期</label><input id="to" v-model="filters.to" class="field-control" type="date" :min="filters.from" /></div><div class="field"><label for="topic">主题</label><select id="topic" v-model="filters.topic" class="field-control"><option value="">全部主题</option><option v-for="topic in TOPICS" :key="topic">{{ topic }}</option></select></div><div class="field"><label for="generation">生成状态</label><select id="generation" v-model="filters.generation" class="field-control"><option value="">全部状态</option><option value="completed">已完成</option><option value="partial">部分完成</option><option value="failed">失败</option></select></div><div class="field"><label for="delivery">推送状态</label><select id="delivery" v-model="filters.delivery" class="field-control"><option value="">全部状态</option><option value="submitted">已提交发送</option><option value="failed">发送失败</option><option value="unknown">状态未知</option><option value="disabled">未启用</option></select></div></div><div v-if="active" class="filter-result"><span class="meta">找到 {{ matched.length }} 份简报</span><button class="button button--ghost" @click="clear"><X :size="14" aria-hidden="true" />清除筛选</button></div></section>
    <EmptyState v-if="!state.briefs.length" title="还没有历史简报" description="生成第一份简报后，它会出现在这里。"><RouterLink class="button button--primary" to="/today">去生成简报</RouterLink></EmptyState>
    <EmptyState v-else-if="!matched.length" title="没有匹配的记录" description="试着扩大日期范围，或清除部分筛选条件。"><button class="button" @click="clear">清除筛选</button></EmptyState>
    <template v-else><div class="history-list"><article v-for="brief in visible" :key="brief.id" class="history-row"><div class="history-date"><strong>{{ brief.date.slice(8) }}</strong><span>{{ brief.date.slice(0, 7) }}</span></div><div class="history-content"><RouterLink :to="`/briefs/${brief.id}`" class="history-title">{{ brief.title }}<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink><p class="meta">{{ brief.items.length }} 条内容 · 版本 {{ brief.version }} · {{ [...new Set(brief.items.map((i) => i.topic))].join(' / ') }}</p><div class="user-status-line"><span>生成</span><Badge :status="brief.generationStatus" /><span>邮件</span><Badge :status="brief.deliveryStatus" /></div></div></article></div><div class="pagination"><label class="meta">每页 <select v-model.number="filters.size" class="field-control"><option :value="20">20 条</option><option :value="50">50 条</option></select></label><span class="meta">共 {{ matched.length }} 份</span><div class="actions"><button class="button button--ghost" aria-label="上一页" :disabled="filters.page <= 1" @click="filters.page--"><ChevronLeft :size="16" /></button><span class="meta">第 {{ filters.page }} / {{ pageCount }} 页</span><button class="button button--ghost" aria-label="下一页" :disabled="filters.page >= pageCount" @click="filters.page++"><ChevronRight :size="16" /></button></div></div></template>
  </div>
</template>
<style scoped>
.history-filters { margin-bottom: 24px; }
.search-field { position: relative; }
.search-field svg { position: absolute; top: 13px; left: 12px; color: var(--color-text-muted); }
.search-field input { padding-left: 40px; }
.filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 20px; }
.filter-result { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
.history-list { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; }
.history-row { display: flex; gap: 24px; padding: 24px; border-bottom: 1px solid var(--color-border); }
.history-row:last-child { border: 0; }
.history-date { flex: 0 0 64px; display: flex; flex-direction: column; justify-content: center; align-items: center; border-right: 1px solid var(--color-border); padding-right: 24px; color: var(--color-text-muted); }
.history-date strong { font-size: 24px; line-height: 32px; color: var(--color-text); font-weight: 500; }
.history-date span { font-size: 11px; white-space: nowrap; }
.history-content { min-width: 0; }
.history-title { font-size: 16px; line-height: 26px; font-weight: 600; color: var(--color-text); text-decoration: none; overflow-wrap: anywhere; }
.history-title:hover { color: var(--color-primary); }
.history-title svg { margin-left: 8px; vertical-align: middle; }
.history-content > p { margin: 8px 0 12px; }
.pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; padding: 16px 0; }
.pagination > label { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
.pagination select { width: auto; }
.pagination .actions { margin-left: auto; }
@media (max-width: 767px) { .filter-grid { grid-template-columns: 1fr; } .history-row { gap: 16px; padding: 20px 16px; } .history-date { flex-basis: 52px; padding-right: 16px; } .history-row .user-status-line { gap: 8px; } }
</style>
