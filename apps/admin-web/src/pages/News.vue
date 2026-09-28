<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, ExternalLink, RefreshCw, Search } from 'lucide-vue-next';
import EmptyState from '@ui/EmptyState.vue';
import { formatDate } from '../lib';
import { newsUrl, useNewsDetail, useNewsList } from '../news';

const route = useRoute(), router = useRouter();
const list = useNewsList(), detail = useNewsDetail();
const { result, sources, loading, error } = list;
const { item, loading: detailLoading, error: detailError } = detail;
const queryText = (value: unknown) => typeof value === 'string' ? value : '';
const filters = computed(() => {
  const page = Number(queryText(route.query.page));
  return { sourceId: queryText(route.query.sourceId), q: queryText(route.query.q), page: Number.isSafeInteger(page) && page > 0 ? page : 1 };
});
const detailId = computed(() => queryText(route.params.id));
const search = ref(''), source = ref('');
const filtered = computed(() => !!filters.value.sourceId || !!filters.value.q);
const sourceName = computed(() => sources.value.find(value => value.id === filters.value.sourceId)?.name);
const listQuery = computed(() => ({
  ...(filters.value.sourceId ? { sourceId: filters.value.sourceId } : {}),
  ...(filters.value.q ? { q: filters.value.q } : {}),
  ...(filters.value.page > 1 ? { page: String(filters.value.page) } : {}),
}));
const backToList = computed(() => ({ path: '/news', query: listQuery.value }));

watch(() => [filters.value.sourceId, filters.value.q, filters.value.page, detailId.value], () => {
  search.value = filters.value.q;
  source.value = filters.value.sourceId;
  if (!detailId.value) void list.load(filters.value);
}, { immediate: true });
watch(() => [route.params.sourceId, detailId.value], () => {
  void detail.load(queryText(route.params.sourceId), detailId.value);
}, { immediate: true });

async function applyFilters() {
  const query = { ...(source.value ? { sourceId: source.value } : {}), ...(search.value.trim() ? { q: search.value.trim() } : {}) };
  if (filters.value.page === 1 && filters.value.sourceId === source.value && filters.value.q === search.value.trim()) await list.load(filters.value);
  else await router.push({ path: '/news', query });
}
function go(page: number) {
  void router.push({ path: '/news', query: { ...listQuery.value, page: page > 1 ? String(page) : undefined } });
}
const newsLocation = (sourceId: string, id: string) => ({ path: `/news/${encodeURIComponent(sourceId)}/${encodeURIComponent(id)}`, query: listQuery.value });
</script>

<template>
  <div class="admin-news">
    <template v-if="detailId">
      <RouterLink class="admin-back" :to="backToList"><ArrowLeft :size="16" aria-hidden="true" />返回缓存新闻</RouterLink>
      <div v-if="detailLoading" class="skeleton" role="status" aria-label="正在加载缓存新闻详情"></div>
      <EmptyState v-else-if="!item" title="无法读取这条缓存新闻" :description="detailError || '新闻可能已过期、被移除，或所属来源已删除。'" error>
        <button class="button" @click="detail.load(queryText(route.params.sourceId), detailId)">重试加载</button>
        <RouterLink class="button" :to="backToList">返回列表</RouterLink>
      </EmptyState>
      <template v-else>
        <header class="page-header"><div><div class="eyebrow">CACHED NEWS</div><h1>{{ item.title }}</h1><p>{{ item.sourceName }} · 发布于 {{ formatDate(item.publishedAt) }}</p></div>
          <a v-if="newsUrl(item.url)" class="button" :href="newsUrl(item.url)" target="_blank" rel="noopener noreferrer">阅读原文<ExternalLink :size="16" aria-hidden="true" /><span class="sr-only">（新窗口）</span></a>
        </header>
        <section class="card news-provenance" aria-label="新闻来源与采集信息">
          <dl class="admin-kv">
            <dt>新闻来源</dt><dd><RouterLink :to="`/sources/${encodeURIComponent(item.sourceId)}`">{{ item.sourceName }}</RouterLink></dd>
            <dt>发布时间</dt><dd>{{ formatDate(item.publishedAt) }}</dd>
            <dt>采集时间</dt><dd>{{ formatDate(item.fetchedAt) }}</dd>
            <dt>首次收录</dt><dd>{{ formatDate(item.firstSeenAt) }}</dd>
            <dt>原文地址</dt><dd><a v-if="newsUrl(item.url)" :href="newsUrl(item.url)" target="_blank" rel="noopener noreferrer">{{ item.url }}<span class="sr-only">（新窗口）</span></a><span v-else>{{ item.url || '未提供原文地址' }}（无法打开）</span></dd>
          </dl>
          <details class="news-trace"><summary>查看采集溯源标识</summary><dl class="admin-kv"><dt>RSS 地址</dt><dd>{{ item.sourceUrl }}</dd><dt>证据 ID</dt><dd class="mono">{{ item.evidenceId }}</dd><dt>快照 ID</dt><dd class="mono">{{ item.snapshotId }}</dd></dl></details>
          <p class="admin-note">时间均为 Asia/Shanghai。以下为采集时缓存的内容，RSS 可能仅提供摘要。</p>
        </section>
        <article class="card news-body" aria-label="缓存新闻内容">
          <template v-if="item.summary && item.summary !== item.content"><h2>来源摘要</h2><p class="news-text">{{ item.summary }}</p></template>
          <template v-if="item.content"><h2>缓存正文</h2><p class="news-text">{{ item.content }}</p></template>
          <p v-if="!item.content" class="muted">{{ item.summary ? '该来源未提供更多正文，可前往原文阅读完整报道。' : '该来源仅缓存了新闻标题和链接，未提供摘要或正文。' }}</p>
        </article>
      </template>
    </template>

    <template v-else>
      <header class="page-header"><div><div class="eyebrow">CACHED NEWS</div><h1>缓存新闻</h1><p>浏览各新闻来源已采集的新闻，按发布时间从新到旧排列。</p></div><button class="button" :disabled="loading" @click="list.load(filters)"><RefreshCw :size="16" aria-hidden="true" />{{ loading ? '正在加载…' : '刷新缓存列表' }}</button></header>
      <p class="admin-note">当前索引保留最近 24 小时发布的新闻；不含发布时间未知的条目。刷新列表仅读取已有缓存。</p>
      <form class="admin-toolbar" @submit.prevent="applyFilters">
        <label class="field">新闻标题<input v-model="search" class="field-control" type="search" maxlength="200" placeholder="按标题搜索全部有效缓存" aria-describedby="news-search-scope"></label>
        <label class="field">新闻来源<select v-model="source" class="field-control" @change="applyFilters"><option value="">全部来源</option><option v-if="source && !sources.some(value => value.id === source)" :value="source">当前来源（{{ source }}）</option><option v-for="entry in sources" :key="entry.id" :value="entry.id">{{ entry.name }}（{{ entry.count }} 条）</option></select></label>
        <button class="button button--primary" type="submit" :disabled="loading"><Search :size="16" aria-hidden="true" />搜索</button>
        <RouterLink v-if="filtered" class="button" to="/news">清除筛选</RouterLink>
      </form>
      <p id="news-search-scope" class="admin-note">搜索覆盖所选来源的全部有效缓存；来源括号内为该来源的缓存总数。</p>
      <div v-if="error && result" class="alert alert--danger news-error" role="alert"><span>{{ error }} 已保留上次加载的数据。</span><button class="button" :disabled="loading" @click="list.load(filters)">重试加载</button></div>
      <div v-if="loading && !result" class="skeleton" role="status" aria-label="正在加载缓存新闻列表"></div>
      <EmptyState v-else-if="error && !result" title="缓存新闻暂不可用" :description="error" error><button class="button" :disabled="loading" @click="list.load(filters)">重试加载</button><RouterLink class="button" to="/sources">查看新闻来源</RouterLink></EmptyState>
      <template v-else-if="result">
        <div class="news-results-heading"><p role="status" class="meta">{{ sourceName || '全部来源' }} · 共 {{ result.total }} 条{{ filters.q ? ` · 关键词：${filters.q}` : '' }}{{ loading ? ' · 正在更新…' : '' }}</p><RouterLink v-if="filters.sourceId" class="admin-subtle-link" :to="`/sources/${encodeURIComponent(filters.sourceId)}`">查看来源与采集状态</RouterLink></div>
        <p class="meta">发布时间范围：{{ formatDate(result.windowStart) }} 至 {{ formatDate(result.windowEnd) }}（Asia/Shanghai）</p>
        <EmptyState v-if="!result.items.length" :title="filtered ? '没有符合条件的缓存新闻' : '暂无缓存新闻'" :description="filtered ? '可调整关键词或切换来源；新闻过期后会退出当前索引。' : '尚无最近 24 小时内发布的已采集新闻，可前往新闻来源检查采集状态。'">
          <RouterLink v-if="filtered" class="button" to="/news">查看全部缓存</RouterLink><RouterLink class="button" :to="filters.sourceId ? `/sources/${encodeURIComponent(filters.sourceId)}` : '/sources'">查看新闻来源</RouterLink>
        </EmptyState>
        <div v-else class="table-wrap" tabindex="0" role="region" aria-label="缓存新闻列表，可横向滚动" :aria-busy="loading"><table class="data-table admin-table news-table"><thead><tr><th scope="col">新闻标题</th><th scope="col">来源</th><th scope="col">发布时间</th><th scope="col">原文</th></tr></thead><tbody>
          <tr v-for="news in result.items" :key="`${news.sourceId}:${news.id}`"><td class="news-title-cell"><RouterLink :to="newsLocation(news.sourceId, news.id)">{{ news.title }}</RouterLink></td><td><RouterLink :to="{ path: '/news', query: { ...(filters.q ? { q: filters.q } : {}), sourceId: news.sourceId } }">{{ news.sourceName }}</RouterLink></td><td class="news-date">{{ formatDate(news.publishedAt) }}</td><td><a v-if="newsUrl(news.url)" class="button button--small" :href="newsUrl(news.url)" target="_blank" rel="noopener noreferrer" :aria-label="`阅读原文：${news.title}（新窗口）`"><ExternalLink :size="16" aria-hidden="true" />原文</a><span v-else class="meta">不可用</span></td></tr>
        </tbody></table></div>
        <nav v-if="result.totalPages > 0" class="admin-pagination" aria-label="缓存新闻分页"><span class="meta">每页 {{ result.pageSize }} 条 · 第 {{ result.page }} / {{ result.totalPages }} 页</span><div class="actions"><button class="button" :disabled="loading || result.page <= 1" @click="go(result.page - 1)">上一页</button><button class="button" :disabled="loading || result.page >= result.totalPages" @click="go(result.page + 1)">下一页</button></div></nav>
      </template>
    </template>
  </div>
</template>
