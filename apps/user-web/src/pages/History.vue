<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Search, ChevronLeft, ChevronRight, CalendarDays, ChevronDown, Newspaper } from 'lucide-vue-next';
import { api, type BriefPage } from '@zhigenews/api-client';
import EmptyState from '@ui/EmptyState.vue';
import LoadingState from '../components/LoadingState.vue';
import { useRequestState } from '../useRequestState';
const route = useRoute(), router = useRouter();
const filters = reactive({ search: String(route.query.q || ''), date: String(route.query.date || '') });
const result = ref<BriefPage>({ items: [], nextCursor: null }), loading = ref(true);
const active = computed(() => !!(route.query.q || route.query.date));
const page = computed(() => Math.max(1, Number(route.query.page) || 1));
const { error, remaining, fail, clear: clearError } = useRequestState();
const pageCursors = reactive(new Map<number, string>([[1, '']]));
let filterKey = '';
let controller: AbortController | undefined, debounce: ReturnType<typeof setTimeout> | undefined;
function apply() {
  clearTimeout(debounce);
  void router.replace({ query: { q: filters.search.trim() || undefined, date: filters.date || undefined } });
}
function schedule() { clearTimeout(debounce); debounce = setTimeout(apply, 350); }
function clear() { filters.search = ''; filters.date = ''; apply(); }
async function load() {
  if (remaining.value) return;
  controller?.abort(); const current = controller = new AbortController();
  loading.value = true; clearError();
  try { result.value = await api<BriefPage>('listBriefs', { query: { q: String(route.query.q || '') || undefined, date: String(route.query.date || '') || undefined, cursor: String(route.query.cursor || '') || undefined, limit: 20 }, signal: current.signal }); }
  catch (exception) { if (!current.signal.aborted) fail(exception); }
  finally { if (!current.signal.aborted) loading.value = false; }
}
function next() {
  if (!result.value.nextCursor) return;
  pageCursors.set(page.value + 1, result.value.nextCursor);
  void router.push({ query: { ...route.query, cursor: result.value.nextCursor, page: page.value + 1 } });
}
function previous() {
  const target = pageCursors.has(page.value - 1) ? page.value - 1 : 1;
  const cursor = pageCursors.get(target);
  void router.push({ query: { ...route.query, cursor: cursor || undefined, page: target > 1 ? target : undefined } });
}
watch(() => route.fullPath, () => {
  filters.search = String(route.query.q || ''); filters.date = String(route.query.date || '');
  const nextKey = JSON.stringify([filters.search, filters.date]);
  if (nextKey !== filterKey) { pageCursors.clear(); pageCursors.set(1, ''); filterKey = nextKey; }
  pageCursors.set(page.value, String(route.query.cursor || ''));
  void load();
}, { immediate: true });
onBeforeUnmount(() => { controller?.abort(); clearTimeout(debounce); });
</script>
<template>
  <div class="user-feed">
    <header class="page-header"><div><h1>历史简报</h1></div></header>
    <section class="history-filters" aria-label="筛选历史简报">
      <div class="search-field"><Search :size="17" aria-hidden="true" /><label for="history-search" class="sr-only">搜索简报</label><input id="history-search" v-model="filters.search" class="field-control" type="search" maxlength="200" placeholder="搜索简报" @input="schedule" @keydown.enter.prevent="apply" /></div>
      <details class="date-filter" :open="!!filters.date"><summary><CalendarDays :size="15" :stroke-width="1.8" aria-hidden="true" />日期筛选<ChevronDown class="disclosure-chevron" :size="14" aria-hidden="true" /></summary><div class="date-fields"><div class="field"><label for="history-date">日期</label><input id="history-date" v-model="filters.date" class="field-control" type="date" @change="apply" /></div></div></details>
      <div v-if="active" class="filter-result"><span class="meta">{{ loading ? '正在查询…' : '按条件筛选' }}</span><button class="button button--ghost" @click="clear">清除筛选</button></div>
    </section>
    <div v-if="error" class="alert alert--danger" role="alert"><span>{{ error }}</span><button class="button" :disabled="remaining > 0" @click="load">{{ remaining ? `${remaining} 秒后可重试` : '重试' }}</button></div>
    <LoadingState v-if="loading" />
    <EmptyState v-else-if="!result.items.length && !error && active" title="没有匹配的简报"><button class="button" @click="clear">清除筛选</button></EmptyState>
    <EmptyState v-else-if="!result.items.length && !error" title="还没有历史简报"><RouterLink class="button button--primary" to="/today">生成简报</RouterLink></EmptyState>
    <template v-else-if="result.items.length">
      <div class="history-list"><article v-for="brief in result.items" :key="brief.id" class="history-row"><div class="history-date"><strong>{{ brief.date.slice(8) }}</strong><span>{{ brief.date.slice(0, 7) }}</span></div><div class="history-content"><RouterLink :to="`/briefs/${brief.id}`" class="history-title">{{ brief.title }}</RouterLink><p class="meta"><span class="news-count"><Newspaper :size="14" :stroke-width="1.8" aria-hidden="true" />{{ brief.items.length }} 条新闻</span><span v-if="brief.generationStatus === 'partial'" class="badge badge--warning">部分完成</span></p></div></article></div>
      <nav v-if="page > 1 || result.nextCursor" class="pagination" aria-label="历史简报分页"><button class="button button--ghost" :aria-label="pageCursors.has(page - 1) ? '上一页' : '返回第一页'" :disabled="page <= 1 || remaining > 0" @click="previous"><ChevronLeft :size="16" /></button><span class="meta">第 {{ page }} 页</span><button class="button button--ghost" aria-label="下一页" :disabled="!result.nextCursor || remaining > 0" @click="next"><ChevronRight :size="16" /></button></nav>
    </template>
  </div>
</template>
<style scoped>
.history-filters { margin-bottom: 16px; }
.search-field { position: relative; }
.search-field svg { position: absolute; top: 13px; left: 12px; color: var(--color-text-muted); }
.search-field input { padding-left: 40px; }
.date-filter { margin-top: 8px; font-size: 13px; color: var(--color-text-secondary); }
.date-filter > summary { display: flex; align-items: center; gap: 6px; padding-block: 12px; min-height: 44px; width: fit-content; cursor: pointer; list-style: none; }
.date-filter > summary::-webkit-details-marker { display: none; }
.date-filter[open] .disclosure-chevron { transform: rotate(180deg); }
.date-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; padding: 8px 0 16px; }
.filter-result { display: flex; justify-content: space-between; align-items: center; }
.history-list { border-top: 1px solid var(--color-border); }
.history-row { display: flex; align-items: center; gap: 24px; padding: 24px 0; border-bottom: 1px solid var(--color-border); }
.history-date { flex: 0 0 66px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 66px; border: 1px solid var(--color-border); border-radius: var(--radius-card); background: var(--color-surface-muted); color: var(--color-text-muted); }
.history-date strong { font-size: 24px; line-height: 32px; color: var(--color-primary); font-weight: 500; }
.history-date span { font-size: 11px; white-space: nowrap; }
.history-content { min-width: 0; }
.history-title { display: inline-block; font-size: 16px; line-height: 26px; font-weight: 600; color: var(--color-text); text-decoration: none; overflow-wrap: anywhere; padding-block: 4px; }
.history-title:hover { color: var(--color-primary); }
.history-content > p { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 4px 0 0; }
.news-count { display: inline-flex; align-items: center; gap: 6px; }
.pagination { display: flex; align-items: center; justify-content: flex-end; gap: 16px; padding-top: 16px; }
@media (max-width: 480px) { .date-fields { grid-template-columns: 1fr; } .history-row { gap: 16px; padding-block: 20px; } .history-date { flex-basis: 52px; } }
</style>
