import { onBeforeUnmount, ref, shallowRef } from 'vue';
import type { CachedNewsDetail, CachedNewsPage, CachedNewsSource } from '@zhigenews/api-client';
import { errorText, request } from './lib';

export type NewsFilters = { sourceId: string; q: string; page: number };

export function useNewsList() {
  const result = shallowRef<CachedNewsPage | null>(null);
  const sources = shallowRef<CachedNewsSource[]>([]);
  const loading = ref(false), error = ref('');
  let revision = 0, key = '';
  let controller: AbortController | undefined;

  async function load(filters: NewsFilters) {
    const current = ++revision;
    controller?.abort();
    const active = controller = new AbortController();
    const nextKey = JSON.stringify(filters);
    if (nextKey !== key) result.value = null;
    key = nextKey;
    loading.value = true;
    error.value = '';
    try {
      const page = await request<CachedNewsPage>('listCachedNews', { query: filters, signal: active.signal });
      if (current !== revision) return;
      result.value = page;
      sources.value = page.sources;
    } catch (err) {
      if (current === revision && !active.signal.aborted) error.value = errorText(err);
    } finally {
      if (current === revision) loading.value = false;
    }
  }
  onBeforeUnmount(() => { revision++; controller?.abort(); });
  return { result, sources, loading, error, load };
}

export function useNewsDetail() {
  const item = shallowRef<CachedNewsDetail | null>(null);
  const loading = ref(false), error = ref('');
  let revision = 0;
  let controller: AbortController | undefined;
  async function load(sourceId: string, id: string) {
    const current = ++revision;
    controller?.abort();
    const active = controller = new AbortController();
    item.value = null;
    error.value = '';
    loading.value = !!id;
    if (!id) return;
    try {
      const detail = await request<CachedNewsDetail>('getCachedNews', { path: { sourceId, id }, signal: active.signal });
      if (current === revision) item.value = detail;
    } catch (err) {
      if (current === revision && !active.signal.aborted) error.value = errorText(err);
    } finally {
      if (current === revision) loading.value = false;
    }
  }
  onBeforeUnmount(() => { revision++; controller?.abort(); });
  return { item, loading, error, load };
}

/** Feed links are external input, including those in cached articles. */
export function newsUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}
