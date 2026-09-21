import { computed, onBeforeUnmount, ref, shallowRef } from 'vue';
import type { Source, SourcePage } from '@zhigenews/api-client';
import { errorText, request } from './lib';

/** Server-filtered pages; selection belongs to the applied query, not a page. */
export function useSourceList() {
  const items = shallowRef<Source[]>([]);
  const search = ref('');
  const selectedIds = ref(new Set<string>());
  const page = ref(1), total = ref(0), totalPages = ref(0), invalidTotal = ref(0);
  const loading = ref(false), loaded = ref(false), error = ref('');
  const refreshing = ref(false);
  const appliedName = ref('');
  let revision = 0;
  let controller: AbortController | undefined;
  const removedIds = new Set<string>();
  const filtered = computed(() => !!appliedName.value);
  const allSelected = computed(() => items.value.length > 0 && items.value.every(item => selectedIds.value.has(item.id)));

  function invalidate() {
    revision++;
    controller?.abort();
    loading.value = refreshing.value = false;
  }

  async function load(targetPage = page.value, background = false) {
    if (background && (loading.value || refreshing.value)) return;
    const current = ++revision;
    controller?.abort();
    controller = new AbortController();
    loading.value = !background || !loaded.value;
    refreshing.value = background && loaded.value;
    error.value = '';
    try {
      const result = await request<SourcePage>('listSources', {
        query: { q: appliedName.value, page: targetPage },
        signal: controller.signal,
      });
      if (current !== revision) return;
      items.value = result.items.filter(item => !removedIds.has(item.id));
      page.value = result.page;
      total.value = result.total;
      totalPages.value = result.totalPages;
      invalidTotal.value = result.invalidTotal;
      loaded.value = true;
    } catch (err) {
      if (current === revision && !controller.signal.aborted) error.value = errorText(err);
    } finally {
      if (current === revision) loading.value = refreshing.value = false;
    }
  }

  async function applyFilters() {
    const name = search.value.trim();
    if (name !== appliedName.value) {
      selectedIds.value = new Set();
      items.value = [];
      loaded.value = false;
      appliedName.value = name;
    }
    await load(1);
  }

  function toggle(id: string) {
    const ids = new Set(selectedIds.value);
    if (ids.has(id)) ids.delete(id); else ids.add(id);
    selectedIds.value = ids;
  }
  function togglePage() {
    const ids = new Set(selectedIds.value);
    for (const item of items.value) {
      if (allSelected.value) ids.delete(item.id); else ids.add(item.id);
    }
    selectedIds.value = ids;
  }
  function forget(ids: string[]) {
    selectedIds.value = new Set([...selectedIds.value].filter(id => !ids.includes(id)));
  }
  function replace(source: Source) {
    items.value = items.value.map(item => item.id === source.id ? source : item);
  }
  function remove(ids: string[]) {
    ids.forEach(id => removedIds.add(id));
    items.value = items.value.filter(item => !removedIds.has(item.id));
    forget(ids);
  }
  const refresh = () => load(page.value, true);
  onBeforeUnmount(invalidate);
  return { items, search, selectedIds, page, total, totalPages, invalidTotal,
    loading, refreshing, loaded, error, filtered, allSelected, load, refresh, invalidate, applyFilters, toggle, togglePage, forget, replace, remove };
}
