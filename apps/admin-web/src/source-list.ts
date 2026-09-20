import { computed, onBeforeUnmount, ref, shallowRef } from 'vue';
import type { Source, SourcePage } from '@zhigenews/api-client';
import { errorText, request } from './lib';

/** Server-filtered pages; selection belongs to the applied query, not a page. */
export function useSourceList() {
  const items = shallowRef<Source[]>([]);
  const search = ref('');
  const kind = ref('all');
  const selectedIds = ref(new Set<string>());
  const page = ref(1), total = ref(0), totalPages = ref(0), invalidTotal = ref(0);
  const loading = ref(false), loaded = ref(false), error = ref('');
  const appliedName = ref(''), appliedKind = ref('all');
  let revision = 0;
  let controller: AbortController | undefined;
  const filtered = computed(() => !!appliedName.value || appliedKind.value !== 'all');
  const allSelected = computed(() => items.value.length > 0 && items.value.every(item => selectedIds.value.has(item.id)));

  async function load(targetPage = page.value) {
    const current = ++revision;
    controller?.abort();
    controller = new AbortController();
    loading.value = true;
    error.value = '';
    try {
      const result = await request<SourcePage>('listSources', {
        query: { q: appliedName.value, kind: appliedKind.value === 'all' ? undefined : appliedKind.value, page: targetPage },
        signal: controller.signal,
      });
      if (current !== revision) return;
      items.value = result.items;
      page.value = result.page;
      total.value = result.total;
      totalPages.value = result.totalPages;
      invalidTotal.value = result.invalidTotal;
      loaded.value = true;
    } catch (err) {
      if (current === revision && !controller.signal.aborted) error.value = errorText(err);
    } finally {
      if (current === revision) loading.value = false;
    }
  }

  async function applyFilters() {
    const name = search.value.trim();
    if (name !== appliedName.value || kind.value !== appliedKind.value) {
      selectedIds.value = new Set();
      items.value = [];
      loaded.value = false;
      appliedName.value = name;
      appliedKind.value = kind.value;
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
  onBeforeUnmount(() => { revision++; controller?.abort(); });
  return { items, search, kind, selectedIds, page, total, totalPages, invalidTotal,
    loading, loaded, error, filtered, allSelected, load, applyFilters, toggle, togglePage, forget, replace };
}
