<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Search, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import { state } from '@shared/mock';
import EmptyState from '@shared/EmptyState.vue';
const route = useRoute(), router = useRouter();
const filters = reactive({ search: String(route.query.q || ''), from: String(route.query.from || ''), to: String(route.query.to || ''), page: Math.max(1, Number(route.query.page) || 1) });
const matched = computed(() => state.briefs.filter((b) => (!filters.search || `${b.title} ${b.summary}`.toLowerCase().includes(filters.search.toLowerCase())) && (!filters.from || b.date >= filters.from) && (!filters.to || b.date <= filters.to)));
const pageCount = computed(() => Math.max(1, Math.ceil(matched.value.length / 20)));
const visible = computed(() => matched.value.slice((filters.page - 1) * 20, filters.page * 20));
const active = computed(() => !!(filters.search || filters.from || filters.to));
watch(() => [filters.search, filters.from, filters.to], () => { filters.page = 1; });
watch(pageCount, (pages) => { filters.page = Math.min(filters.page, pages); }, { immediate: true });
watch(filters, () => { router.replace({ query: { q: filters.search || undefined, from: filters.from || undefined, to: filters.to || undefined, page: filters.page > 1 ? filters.page : undefined } }); });
function clear() { Object.assign(filters, { search: '', from: '', to: '', page: 1 }); }
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><h1>历史简报</h1></div></header>
    <section class="history-filters" aria-label="筛选历史简报">
      <div class="search-field"><Search :size="17" aria-hidden="true" /><label for="history-search" class="sr-only">搜索简报</label><input id="history-search" v-model="filters.search" class="field-control" type="search" placeholder="搜索简报" /></div>
      <details class="date-filter" :open="!!(filters.from || filters.to)"><summary>日期筛选</summary><div class="date-fields"><div class="field"><label for="history-from">起始日期</label><input id="history-from" v-model="filters.from" class="field-control" type="date" :max="filters.to || undefined" /></div><div class="field"><label for="history-to">结束日期</label><input id="history-to" v-model="filters.to" class="field-control" type="date" :min="filters.from || undefined" /></div></div></details>
      <div v-if="active && matched.length" class="filter-result"><span class="meta">{{ matched.length }} 份简报</span><button class="button button--ghost" @click="clear">清除筛选</button></div>
    </section>
    <EmptyState v-if="!state.briefs.length" title="还没有历史简报"><RouterLink class="button button--primary" to="/today">生成简报</RouterLink></EmptyState>
    <EmptyState v-else-if="!matched.length" title="没有匹配的简报"><button class="button" @click="clear">清除筛选</button></EmptyState>
    <template v-else>
      <div class="history-list"><article v-for="brief in visible" :key="brief.id" class="history-row"><div class="history-date"><strong>{{ brief.date.slice(8) }}</strong><span>{{ brief.date.slice(0, 7) }}</span></div><div class="history-content"><RouterLink :to="`/briefs/${brief.id}`" class="history-title">{{ brief.title }}</RouterLink><p class="meta">{{ brief.items.length }} 条新闻<span v-if="brief.generationStatus === 'partial'"> · 部分完成</span></p></div></article></div>
      <nav v-if="pageCount > 1" class="pagination" aria-label="历史简报分页"><button class="button button--ghost" aria-label="上一页" :disabled="filters.page <= 1" @click="filters.page--"><ChevronLeft :size="16" /></button><span class="meta">{{ filters.page }} / {{ pageCount }}</span><button class="button button--ghost" aria-label="下一页" :disabled="filters.page >= pageCount" @click="filters.page++"><ChevronRight :size="16" /></button></nav>
    </template>
  </div>
</template>
<style scoped>
.history-filters { margin-bottom: 16px; }
.search-field { position: relative; }
.search-field svg { position: absolute; top: 13px; left: 12px; color: var(--color-text-muted); }
.search-field input { padding-left: 40px; }
.date-filter { margin-top: 8px; font-size: 13px; color: var(--color-text-secondary); }
.date-filter > summary { padding-block: 12px; min-height: 44px; width: fit-content; cursor: pointer; }
.date-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; padding: 8px 0 16px; }
.filter-result { display: flex; justify-content: space-between; align-items: center; }
.history-list { border-top: 1px solid var(--color-border); }
.history-row { display: flex; align-items: center; gap: 24px; padding: 24px 0; border-bottom: 1px solid var(--color-border); }
.history-date { flex: 0 0 66px; display: flex; flex-direction: column; align-items: center; color: var(--color-text-muted); }
.history-date strong { font-size: 24px; line-height: 32px; color: var(--color-text); font-weight: 500; }
.history-date span { font-size: 11px; white-space: nowrap; }
.history-content { min-width: 0; }
.history-title { display: inline-block; font-size: 16px; line-height: 26px; font-weight: 600; color: var(--color-text); text-decoration: none; overflow-wrap: anywhere; padding-block: 4px; }
.history-title:hover { color: var(--color-primary); }
.history-content > p { margin: 4px 0 0; }
.pagination { display: flex; align-items: center; justify-content: flex-end; gap: 16px; padding-top: 16px; }
@media (max-width: 480px) { .date-fields { grid-template-columns: 1fr; } .history-row { gap: 16px; padding-block: 20px; } .history-date { flex-basis: 52px; } }
</style>
